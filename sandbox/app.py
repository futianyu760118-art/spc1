"""技能脚本沙箱：无网络容器内执行技能 scripts/ 下的脚本。

安全边界：
- 容器无网络、只读根文件系统、非 root、cap_drop ALL；
- 每次请求只接收一个技能 zip，解压到独立临时目录；
- 仅允许 scripts/ 下 .py/.js/.cjs/.mjs/.sh；
- 限时、限内存、限输出、限文件大小；
- 输入 params 通过 stdin JSON 传入。
"""

import asyncio
import base64
import hmac
import io
import json
import os
import shutil
import signal
import stat
import sys
import tempfile
import time
import zipfile

try:
    import resource
except ImportError:  # Windows 本地调试不支持 POSIX rlimit
    resource = None
from pathlib import Path, PurePosixPath
from typing import Dict, Optional, Tuple

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

SANDBOX_TOKEN = os.environ.get("SANDBOX_TOKEN", "").strip()
MAX_PACKAGE_BYTES = int(os.environ.get("SANDBOX_MAX_PACKAGE_BYTES", "20971520"))
MAX_TIMEOUT_S = int(os.environ.get("SANDBOX_MAX_TIMEOUT_S", "60"))
DEP_INSTALL_TIMEOUT_S = int(os.environ.get("SANDBOX_DEP_INSTALL_TIMEOUT_S", "60"))
DEPS_DIR = ".deps"
MAX_OUTPUT_BYTES = int(os.environ.get("SANDBOX_MAX_OUTPUT_BYTES", "65536"))
MAX_FILES = 500
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_SCRIPT_BYTES = 5 * 1024 * 1024
WORK_ROOT = Path(os.environ.get("SANDBOX_WORK_ROOT", "/tmp"))

SCRIPT_RUNTIMES = {
    ".py": [sys.executable],
    ".js": ["node"],
    ".cjs": ["node"],
    ".mjs": ["node"],
    ".sh": ["bash"],
}
MAX_ARTIFACT_FILES = 20
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
MAX_INPUT_FILES = 10
MAX_INPUT_BYTES = 512 * 1024
ARTIFACT_SKIP_DIRS = {"__pycache__", "tmp", ".git", ".cache", DEPS_DIR}
ARTIFACT_SKIP_NAMES = {"wps_stats.db"}
ARTIFACT_SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}

app = FastAPI(title="SPC Skill Sandbox", docs_url=None, redoc_url=None, openapi_url=None)


def _snapshot(work: Path) -> Dict[str, tuple]:
    snapshot: Dict[str, tuple] = {}
    for path in work.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(work).as_posix()
        if any(part in ARTIFACT_SKIP_DIRS for part in PurePosixPath(relative).parts):
            continue
        stat_result = path.stat()
        snapshot[relative] = (stat_result.st_size, stat_result.st_mtime_ns)
    return snapshot


def _collect_artifacts(work: Path, before: Dict[str, tuple]) -> tuple:
    files = []
    total = 0
    truncated = False
    for path in sorted(work.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(work).as_posix()
        if any(part in ARTIFACT_SKIP_DIRS for part in PurePosixPath(relative).parts):
            continue
        if path.name.startswith("."):
            continue
        if path.name in ARTIFACT_SKIP_NAMES or path.suffix.lower() in ARTIFACT_SKIP_SUFFIXES:
            continue
        stat_result = path.stat()
        signature = (stat_result.st_size, stat_result.st_mtime_ns)
        if before.get(relative) == signature:
            continue
        if len(files) >= MAX_ARTIFACT_FILES or total + stat_result.st_size > MAX_ARTIFACT_BYTES:
            truncated = True
            break
        files.append((relative, path.read_bytes()))
        total += stat_result.st_size
    return files, truncated


def _zip_artifacts(files: list) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative, content in files:
            archive.writestr(relative, content)
    return buffer.getvalue()


def _check_token(token: Optional[str]) -> None:
    if not SANDBOX_TOKEN:
        raise HTTPException(status_code=503, detail="sandbox token not configured")
    if not token or not hmac.compare_digest(token, SANDBOX_TOKEN):
        raise HTTPException(status_code=401, detail="invalid sandbox token")


def _normalize_name(name: str) -> Optional[str]:
    raw = (name or "").replace("\\", "/")
    if not raw or "\x00" in raw:
        raise HTTPException(status_code=400, detail="invalid package filename")
    while raw.startswith("./"):
        raw = raw[2:]
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or ":" in raw:
        raise HTTPException(status_code=400, detail=f"invalid package path: {name}")
    if raw.startswith("__MACOSX/") or raw.endswith("/.DS_Store") or raw == ".DS_Store":
        return None
    return path.as_posix()


def _extract_package(data: bytes, target: Path) -> None:
    if len(data) > MAX_PACKAGE_BYTES:
        raise HTTPException(status_code=413, detail="package too large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="invalid zip package")
    infos = archive.infolist()
    if not infos or len(infos) > MAX_FILES:
        raise HTTPException(status_code=400, detail="invalid package file count")
    total = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise HTTPException(status_code=400, detail="encrypted zip is not supported")
        mode = info.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise HTTPException(status_code=400, detail="symlink is not allowed")
        total += int(info.file_size)
        if total > MAX_PACKAGE_BYTES:
            raise HTTPException(status_code=413, detail="uncompressed package too large")
        if int(info.file_size) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"file too large: {info.filename}")
    target.mkdir(parents=True, exist_ok=True)
    for info in infos:
        if info.is_dir():
            continue
        name = _normalize_name(info.filename)
        if name is None:
            continue
        destination = (target / name).resolve()
        if not destination.is_relative_to(target.resolve()):
            raise HTTPException(status_code=400, detail="package path traversal")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, open(destination, "wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
    if not (target / "SKILL.md").is_file():
        raise HTTPException(status_code=400, detail="package missing SKILL.md")


def _write_input_files(work: Path, inputs: dict) -> None:
    if not isinstance(inputs, dict):
        raise HTTPException(status_code=400, detail="input_files must be an object")
    if len(inputs) > MAX_INPUT_FILES:
        raise HTTPException(status_code=400, detail="too many input files")
    total = 0
    for relative, content in inputs.items():
        if not isinstance(relative, str) or not isinstance(content, str):
            raise HTTPException(status_code=400, detail="input_files must be string map")
        name = _normalize_name(relative)
        if name is None:
            raise HTTPException(status_code=400, detail=f"invalid input file: {relative}")
        if name == "SKILL.md" or name.startswith("scripts/"):
            raise HTTPException(status_code=400, detail="input_files cannot overwrite skill files")
        encoded = content.encode("utf-8")
        total += len(encoded)
        if total > MAX_INPUT_BYTES:
            raise HTTPException(status_code=413, detail="input_files too large")
        target = (work / name).resolve()
        if not target.is_relative_to(work.resolve()):
            raise HTTPException(status_code=400, detail=f"invalid input file: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _rewrite_file_args(args: list, work: Path) -> list:
    """把脚本参数中的文件路径改为沙箱工作目录内的实际文件。

    Skill 脚本常用 --input_file 等参数接收文件，绝对路径会指向后端容器
    或宿主机；这里统一改写为解压后的工作目录路径，找不到则保持原值。
    """
    file_flags = {
        "--input_file", "-i", "--input", "--file",
        "--authoring_file", "--outline_file", "--annotations_file",
    }
    rewritten = list(args or [])
    work = work.resolve()
    for index in range(len(rewritten) - 1):
        flag = rewritten[index]
        if flag not in file_flags and not flag.endswith("_file"):
            continue
        value = rewritten[index + 1]
        if not value or value.startswith("-"):
            continue
        candidate = Path(value)
        target = None
        if candidate.is_absolute():
            try:
                if candidate.is_relative_to(work) and candidate.is_file():
                    continue
            except ValueError:
                pass
            target = (work / candidate.name).resolve()
        else:
            target = (work / value).resolve()
        try:
            if target.is_relative_to(work) and target.is_file():
                rewritten[index + 1] = str(target)
        except ValueError:
            pass
    return rewritten


def _limit_resources() -> None:
    """子进程资源限制（Linux）；失败不阻断（沙箱外层仍有容器限额）。"""
    try:
        os.setsid()
    except OSError:
        pass
    if resource is None:
        return
    limits = [
        (resource.RLIMIT_CPU, 60),
        (resource.RLIMIT_AS, 512 * 1024 * 1024),
        (resource.RLIMIT_FSIZE, 16 * 1024 * 1024),
        (resource.RLIMIT_NOFILE, 64),
    ]
    if hasattr(resource, "RLIMIT_NPROC"):
        limits.append((resource.RLIMIT_NPROC, 64))
    for item, value in limits:
        try:
            resource.setrlimit(item, (value, value))
        except (ValueError, OSError):
            pass


async def _read_limited(stream: asyncio.StreamReader, limit: int) -> Tuple[bytes, bool]:
    chunks = []
    total = 0
    truncated = False
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        total += len(chunk)
        if total <= limit:
            chunks.append(chunk)
        else:
            truncated = True
    return b"".join(chunks), truncated


def _kill_process_group(proc) -> None:
    if os.name == "posix" and hasattr(os, "killpg"):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError):
            return
    try:
        proc.kill()
    except ProcessLookupError:
        pass


def _sandbox_env(work: Path) -> dict:
    deps = work / DEPS_DIR
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(work),
        "TMPDIR": str(work / "tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NODE_NO_WARNINGS": "1",
        "PIP_NO_CACHE_DIR": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_ROOT_USER_ACTION": "ignore",
    }
    python_paths = [str(deps)] if deps.is_dir() else []
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        python_paths.extend(item for item in existing.split(os.pathsep) if item)
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
    node_modules = deps / "node_modules"
    if node_modules.is_dir():
        env["NODE_PATH"] = str(node_modules)
    return env


async def _run_install_command(command: list, work: Path, timeout_s: int) -> Dict:
    env = _sandbox_env(work)
    (work / "tmp").mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(work),
        env=env,
        preexec_fn=_limit_resources if os.name == "posix" else None,
    )
    stdout_task = asyncio.create_task(_read_limited(proc.stdout, MAX_OUTPUT_BYTES))
    stderr_task = asyncio.create_task(_read_limited(proc.stderr, MAX_OUTPUT_BYTES))
    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        timed_out = True
        _kill_process_group(proc)
        await proc.wait()
    stdout, out_truncated = await stdout_task
    stderr, err_truncated = await stderr_task
    return {
        "ok": proc.returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "truncated": out_truncated or err_truncated,
    }


async def _install_dependencies(work: Path) -> None:
    """安装技能包声明的 requirements.txt / package.json 依赖。

    依赖统一安装到工作目录的 .deps 下，避免写入只读根文件系统；
    安装失败或超时直接报错，不带缺失依赖继续执行脚本。
    """
    requirements = work / "requirements.txt"
    package_json = work / "package.json"
    deps = work / DEPS_DIR
    if not requirements.is_file() and not package_json.is_file():
        return
    deps.mkdir(parents=True, exist_ok=True)
    if requirements.is_file():
        result = await _run_install_command(
            [
                sys.executable, "-m", "pip", "install",
                "--target", str(deps),
                "--no-cache-dir",
                "--disable-pip-version-check",
                "--no-input",
                "--progress-bar", "off",
                "--retries", "3",
                "--timeout", "30",
                "-r", str(requirements),
            ],
            work, DEP_INSTALL_TIMEOUT_S,
        )
        if not result["ok"]:
            detail = (result["stderr"] or result["stdout"] or "dependency install failed").strip()
            raise HTTPException(
                status_code=400,
                detail=f"dependency install failed: {detail[:500]}",
            )
    if package_json.is_file():
        npm = shutil.which("npm")
        if npm is None:
            raise HTTPException(
                status_code=400,
                detail="dependency install failed: npm is not available in sandbox",
            )
        shutil.copyfile(package_json, deps / "package.json")
        lock_file = work / "package-lock.json"
        if lock_file.is_file():
            shutil.copyfile(lock_file, deps / "package-lock.json")
        result = await _run_install_command(
            [
                npm, "install", "--prefix", str(deps),
                "--ignore-scripts", "--omit=dev", "--no-audit", "--no-fund",
            ],
            work, DEP_INSTALL_TIMEOUT_S,
        )
        if not result["ok"]:
            detail = (result["stderr"] or result["stdout"] or "npm install failed").strip()
            raise HTTPException(
                status_code=400,
                detail=f"dependency install failed: {detail[:500]}",
            )


async def _execute(
    command: list, script_path: Path, work: Path, params_json: str, timeout_s: int,
    script_args: Optional[list] = None,
) -> Dict:
    env = _sandbox_env(work)
    (work / "tmp").mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *command, *[str(arg) for arg in (script_args or [])],
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(work),
        env=env,
        preexec_fn=_limit_resources if os.name == "posix" else None,
    )
    stdout_task = asyncio.create_task(_read_limited(proc.stdout, MAX_OUTPUT_BYTES))
    stderr_task = asyncio.create_task(_read_limited(proc.stderr, MAX_OUTPUT_BYTES))
    timed_out = False
    try:
        try:
            proc.stdin.write(params_json.encode("utf-8"))
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass
        await asyncio.wait_for(proc.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        timed_out = True
        _kill_process_group(proc)
        await proc.wait()
    stdout, out_truncated = await stdout_task
    stderr, err_truncated = await stderr_task
    _kill_process_group(proc)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    if timed_out:
        return {
            "ok": False, "exit_code": None,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": f"脚本执行超时（{timeout_s}s）",
            "duration_ms": duration_ms, "truncated": out_truncated or err_truncated,
        }
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "duration_ms": duration_ms,
        "truncated": out_truncated or err_truncated,
    }


@app.get("/health")
async def health():
    return {"ok": True, "token_configured": bool(SANDBOX_TOKEN)}


async def run_task(
    data: bytes,
    script: str,
    parsed_params: dict,
    parsed_args: list,
    parsed_inputs: dict,
    timeout_s: int,
) -> Dict:
    if len(data) > MAX_PACKAGE_BYTES:
        raise HTTPException(status_code=413, detail="package too large")
    if not isinstance(parsed_params, dict):
        raise HTTPException(status_code=400, detail="params must be an object")
    if not isinstance(parsed_args, list) or not all(isinstance(item, str) for item in parsed_args):
        raise HTTPException(status_code=400, detail="args must be an array of strings")
    if len(parsed_args) > 32 or any(len(item) > 2000 or "\x00" in item for item in parsed_args):
        raise HTTPException(status_code=400, detail="args too large")
    if not isinstance(parsed_inputs, dict):
        raise HTTPException(status_code=400, detail="input_files must be an object")
    normalized = (script or "").strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized.startswith("scripts/")
        or path.is_absolute()
        or ".." in path.parts
        or ":" in normalized
        or "\x00" in normalized
    ):
        raise HTTPException(status_code=400, detail="script must be under scripts/")
    suffix = path.suffix.lower()
    command = SCRIPT_RUNTIMES.get(suffix)
    if command is None:
        raise HTTPException(status_code=400, detail=f"unsupported script type: {suffix}")

    timeout_s = max(1, min(int(timeout_s or 30), MAX_TIMEOUT_S))
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skill-run-", dir=str(WORK_ROOT)) as tmp:
        work = Path(tmp)
        _extract_package(data, work)
        _write_input_files(work, parsed_inputs)
        await _install_dependencies(work)
        parsed_args = _rewrite_file_args(parsed_args, work)
        script_path = (work / normalized).resolve()
        if not script_path.is_relative_to(work.resolve()) or not script_path.is_file():
            raise HTTPException(status_code=400, detail="script not found")
        if script_path.is_symlink():
            raise HTTPException(status_code=400, detail="script symlink is not allowed")
        if script_path.stat().st_size > MAX_SCRIPT_BYTES:
            raise HTTPException(status_code=413, detail="script too large")
        if shutil.which(command[0]) is None:
            raise HTTPException(status_code=503, detail=f"runtime not available: {suffix}")
        before = _snapshot(work)
        result = await _execute(
            [*command, str(script_path)],
            script_path, work,
            json.dumps(parsed_params, ensure_ascii=False),
            timeout_s,
            script_args=parsed_args,
        )
        artifacts, truncated = _collect_artifacts(work, before)
        if artifacts:
            result["artifacts"] = base64.b64encode(_zip_artifacts(artifacts)).decode("ascii")
            result["artifact_files"] = [
                {"path": relative, "size": len(content)}
                for relative, content in artifacts
            ]
            result["artifacts_truncated"] = truncated
    return result


@app.post("/run")
async def run(
    package: UploadFile = File(...),
    script: str = Form(...),
    params: str = Form("{}"),
    args: str = Form("[]"),
    input_files: str = Form("{}"),
    timeout_s: int = Form(30),
    x_sandbox_token: Optional[str] = Header(default=None),
):
    _check_token(x_sandbox_token)
    data = await package.read()
    try:
        parsed_params = json.loads(params or "{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="params must be valid JSON")
    try:
        parsed_args = json.loads(args or "[]")
    except ValueError:
        raise HTTPException(status_code=400, detail="args must be valid JSON")
    try:
        parsed_inputs = json.loads(input_files or "{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="input_files must be valid JSON")
    return await run_task(data, script, parsed_params, parsed_args, parsed_inputs, timeout_s)
