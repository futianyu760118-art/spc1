"""问题反馈 AI 自动实现 Runner。

长轮询等待后端问题反馈队列（ai_status=queued），认领后：
1. 在独立 git worktree + ai-feedback/<id> 分支上运行 claude CLI 修改代码；
2. 按改动范围执行门禁（backend pytest / frontend build / 敏感文件扫描）；
3. 通过后本地提交并回写反馈结果（ai-finish），失败则回写失败原因。

设计与约定见 docs/superpowers/specs/2026-09-29-feedback-ai-autofix-design.md、
docs/superpowers/specs/2026-09-30-feedback-ai-progress-design.md。
运行：<python.exe> runner.py [--config config.local.json] [--once] [--cleanup]
注意：.runner.lock 仅保证同一工作目录单实例；同一后端应只运行一个 runner 实例。
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

RUNNER_DIR = Path(__file__).resolve().parent
REPO_DIR_DEFAULT = RUNNER_DIR.parents[1]
LOCK_FILE = RUNNER_DIR / ".runner.lock"
STOP = {"requested": False}
PROGRESS_FLUSH_SECONDS = 5.0
PROGRESS_MAX_ACTIONS_PER_POST = 20
PROGRESS_REQUEST_TIMEOUT_SECONDS = 5.0
WAIT_TIMEOUT_SECONDS = 20


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


class RunFailure(Exception):
    """单条反馈处理失败（原因会回写到反馈单）。"""


def run_command(cmd, cwd=None, timeout=None, check=False, shell=False, env=None):
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=shell,
        env=env,
    )
    if check and result.returncode != 0:
        raise RunFailure(f"命令失败({result.returncode}): {cmd}\n{result.stderr[-2000:]}")
    return result


def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"配置文件不存在: {path}（复制 config.example.json 为 config.local.json 并填写）")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in ("base_url", "username", "password") if not cfg.get(key)]
    if missing:
        raise SystemExit(f"配置缺少必填项: {', '.join(missing)}")
    cfg.setdefault("poll_interval_seconds", 10)
    cfg.setdefault("repo_dir", str(REPO_DIR_DEFAULT))
    cfg.setdefault("base_branch", "HEAD")
    cfg.setdefault(
        "worktrees_dir",
        str(REPO_DIR_DEFAULT.parent / f"{REPO_DIR_DEFAULT.name}-ai-worktrees"),
    )
    cfg.setdefault("backend_python", "python")
    if not isinstance(cfg.get("gates"), dict):
        cfg["gates"] = {}
    if not isinstance(cfg.get("claude"), dict):
        cfg["claude"] = {}
    try:
        cfg["poll_interval_seconds"] = max(1, int(cfg["poll_interval_seconds"]))
    except (TypeError, ValueError):
        raise SystemExit("poll_interval_seconds 必须是整数")
    cfg["gates"].setdefault("backend_command", "{python} -m pytest -q")
    cfg["gates"].setdefault("frontend_command", "npm run build")
    cfg["gates"].setdefault("timeout_minutes", 30)
    cfg["claude"].setdefault("command", "claude")
    cfg["claude"].setdefault("timeout_minutes", 60)
    cfg["claude"].setdefault("permission_mode", "acceptEdits")
    cfg["claude"].setdefault("dangerously_skip_permissions", False)
    try:
        cfg["gates"]["timeout_minutes"] = max(1, int(cfg["gates"]["timeout_minutes"]))
        cfg["claude"]["timeout_minutes"] = max(1, int(cfg["claude"]["timeout_minutes"]))
    except (TypeError, ValueError):
        raise SystemExit("timeout_minutes 必须是整数")
    cfg["claude"].setdefault("allowed_tools", [
        "Read", "Edit", "Write", "Glob", "Grep",
        "Bash(python -m pytest:*)", "Bash(py -m pytest:*)",
        "Bash(npm run build:*)", "Bash(npx tsc:*)",
        "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
        "Bash(git show:*)", "Bash(git rev-parse:*)", "Bash(cd:*)", "Bash(ls:*)",
        "Bash(head:*)", "Bash(tail:*)", "Bash(cat:*)",
    ])
    cfg.setdefault("blocked_globs", [
        ".env", ".env.*", "*.env", "**/.env", "**/.env.*", "**/*.env",
        "scripts/deploy-*", "**/scripts/deploy-*", "docker-compose-prod.yml",
    ])
    return cfg


class ApiClient:
    """后端 API 客户端：登录、拉队列、认领、回写。"""

    def __init__(self, base_url: str, username: str, password: str):
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=30)
        self._username = username
        self._password = password
        self._token: str | None = None

    def _json(self, response: httpx.Response) -> dict:
        try:
            return response.json()
        except ValueError:
            raise RuntimeError(
                f"响应不是 JSON（HTTP {response.status_code}）: {(response.text or '')[:200]}"
            )

    def _login(self) -> None:
        response = self._client.post(
            "/api/v1/basicdata/auth/login",
            data={"username": self._username, "password": self._password, "login_type": "employee"},
        )
        body = self._json(response)
        if body.get("code") != 0 or not body.get("data"):
            raise RuntimeError(f"登录失败: {body.get('message') or response.status_code}")
        self._token = body["data"]["access_token"]

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if not self._token:
            self._login()
        headers = {"Authorization": f"Bearer {self._token}"}
        response = self._client.request(method, url, headers=headers, **kwargs)
        if response.status_code == 401:
            self._token = None
            self._login()
            headers = {"Authorization": f"Bearer {self._token}"}
            response = self._client.request(method, url, headers=headers, **kwargs)
        return response

    def claim(self, feedback_id: int) -> dict | None:
        response = self._request("POST", f"/api/v1/basicdata/feedback/{feedback_id}/ai-claim")
        if response.status_code == 409:
            return None
        body = self._json(response)
        if body.get("code") != 0:
            raise RuntimeError(f"认领失败: {body.get('message')}")
        return body["data"]

    def finish(self, feedback_id: int, success: bool, branch: str | None = None,
               summary: str | None = None, error: str | None = None) -> None:
        response = self._request("POST", f"/api/v1/basicdata/feedback/{feedback_id}/ai-finish", json={
            "success": success,
            "branch": branch,
            "summary": summary,
            "error": error,
        })
        body = self._json(response)
        if body.get("code") != 0:
            raise RuntimeError(f"回写结果失败: {body.get('message')}")

    def wait_queued(self, timeout_seconds: int) -> list[int]:
        response = self._request(
            "GET",
            "/api/v1/basicdata/feedback/ai-queue-wait",
            params={"timeout_seconds": timeout_seconds},
            timeout=timeout_seconds + 10,
        )
        body = self._json(response)
        if body.get("code") != 0:
            raise RuntimeError(f"等待队列失败: {body.get('message')}")
        return list(body["data"].get("ids") or [])

    def progress(self, feedback_id: int, stage: str | None = None,
                 actions: list[str] | None = None) -> None:
        payload: dict = {}
        if stage:
            payload["stage"] = stage
        if actions:
            payload["actions"] = actions
        response = self._request(
            "POST",
            f"/api/v1/basicdata/feedback/{feedback_id}/ai-progress",
            json=payload,
            timeout=PROGRESS_REQUEST_TIMEOUT_SECONDS,
        )
        body = self._json(response)
        if body.get("code") != 0:
            raise RuntimeError(f"进度上报失败: {body.get('message')}")

    def get_bytes(self, url: str) -> bytes:
        response = self._request("GET", url)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        return response.content

    def close(self) -> None:
        self._client.close()


class ProgressReporter:
    """AI 进度上报（尽力而为）：阶段即时上报，动作节流批量上报；失败只记日志。"""

    def __init__(self, api: ApiClient, feedback_id: int):
        self._api = api
        self._feedback_id = feedback_id
        self._buffer: list[str] = []
        self._last_flush = time.monotonic()

    def stage(self, name: str) -> None:
        self.flush()
        self._post(stage=name)

    def action(self, text: str) -> None:
        self._buffer.append(text)
        if len(self._buffer) >= PROGRESS_MAX_ACTIONS_PER_POST:
            self.flush()
        elif time.monotonic() - self._last_flush >= PROGRESS_FLUSH_SECONDS:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        batch, self._buffer = self._buffer, []
        self._last_flush = time.monotonic()
        self._post(actions=batch)

    def _post(self, stage: str | None = None, actions: list[str] | None = None) -> None:
        try:
            self._api.progress(self._feedback_id, stage=stage, actions=actions)
        except Exception as exc:
            log(f"进度上报失败（不影响任务）: {exc}")


def acquire_lock() -> None:
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(
            f"检测到 {LOCK_FILE}，runner 可能已在运行；确认无进程后删除该文件再启动"
        )
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)


def release_lock() -> None:
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def git(cfg: dict, *args: str, check: bool = True, cwd: Path | None = None):
    return run_command(["git", *args], cwd=cwd or Path(cfg["repo_dir"]), check=check)


def resolve_base_branch(cfg: dict) -> str:
    if cfg["base_branch"] != "HEAD":
        return cfg["base_branch"]
    result = git(cfg, "rev-parse", "--abbrev-ref", "HEAD", check=True)
    return result.stdout.strip()


def changed_files(worktree: Path) -> list[str]:
    result = run_command(
        ["git", "-c", "core.quotepath=false", "status", "--porcelain"],
        cwd=worktree, check=True,
    )
    files: list[str] = []
    for line in (result.stdout or "").splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip('"').replace("\\", "/"))
    return files


def committed_changes(worktree: Path, base_sha: str) -> list[str]:
    """代理自行 commit 时，取其相对基线提交的文件清单。"""
    result = run_command(["git", "diff", "--name-only", base_sha, "HEAD"], cwd=worktree, check=True)
    return [line.strip().replace("\\", "/") for line in (result.stdout or "").splitlines() if line.strip()]


def load_env_values(repo_dir: Path) -> dict[str, str]:
    """从主仓库 .env 系列文件解析键值（不落日志），供门禁子进程注入环境变量。"""
    env: dict[str, str] = {}
    for relative in ("backend/.env.local", ".env.local", "backend/.env", ".env"):
        path = repo_dir / relative
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def ensure_node_modules(worktree: Path, repo_dir: Path) -> None:
    """为 worktree 前端门禁创建指向主仓库 node_modules 的链接（不复制、不提交）。"""
    link = worktree / "frontend" / "node_modules"
    if link.exists():
        return
    source = repo_dir / "frontend" / "node_modules"
    if not source.exists():
        raise RunFailure(f"主仓库缺少 {source}，请先在主仓库执行 npm install 再跑前端门禁")
    if os.name == "nt":
        result = run_command(["cmd", "/c", "mklink", "/J", str(link), str(source)])
    else:
        result = run_command(["ln", "-s", str(source), str(link)])
    if result.returncode != 0:
        raise RunFailure(f"node_modules 链接失败: {(result.stderr or '').strip()}")


def remove_node_modules_link(worktree: Path) -> None:
    link = worktree / "frontend" / "node_modules"
    if not link.exists():
        return
    if os.name == "nt":
        run_command(["cmd", "/c", "rmdir", str(link)], check=False)
    else:
        run_command(["rm", str(link)], check=False)


def wait_for(seconds: float) -> None:
    """可被 Ctrl+C 打断的等待。"""
    deadline = time.monotonic() + seconds
    while not STOP["requested"] and time.monotonic() < deadline:
        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))


def sensitive_hits(cfg: dict, files: list[str]) -> list[str]:
    hits: list[str] = []
    for path in files:
        for pattern in cfg["blocked_globs"]:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch("/" + path, "/" + pattern):
                hits.append(path)
                break
    return hits


def prepare_worktree(cfg: dict, feedback: dict) -> tuple[Path, str, str]:
    feedback_id = feedback["id"]
    worktrees_dir = Path(cfg["worktrees_dir"])
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    worktree = worktrees_dir / f"fb-{feedback_id}"
    branch = f"ai-feedback/{feedback_id}"
    if worktree.exists():
        git(cfg, "worktree", "remove", "--force", str(worktree), check=False)
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
    git(cfg, "worktree", "prune", check=False)
    git(cfg, "branch", "-D", branch, check=False)
    git(cfg, "worktree", "add", "-b", branch, str(worktree), cfg["base_branch"], check=True)
    base_sha = git(cfg, "rev-parse", "HEAD", cwd=worktree, check=True).stdout.strip()
    log(f"worktree 就绪: {worktree}（分支 {branch}，基线 {base_sha[:8]}）")
    return worktree, branch, base_sha


def download_attachments(api: ApiClient, feedback: dict, run_dir: Path) -> list[Path]:
    attachments = feedback.get("attachments") or []
    if not attachments:
        return []
    target_dir = run_dir / "attachments"
    target_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for attachment in attachments:
        url = attachment.get("url") or ""
        if not url:
            continue
        name = re.sub(r"[^\w\u4e00-\u9fff.-]", "_", attachment.get("name") or "attachment")
        try:
            (target_dir / name).write_bytes(api.get_bytes(url))
            saved.append(target_dir / name)
        except Exception as exc:
            log(f"附件下载失败 {name}: {exc}")
    return saved


def build_prompt(feedback: dict, attachments: list[Path]) -> str:
    template = (RUNNER_DIR / "prompts" / "fix-feedback.md").read_text(encoding="utf-8")
    attachment_text = "\n".join(f"- {path}" for path in attachments) or "（无）"
    replacements = {
        "{{id}}": str(feedback["id"]),
        "{{type}}": feedback.get("type") or "",
        "{{severity}}": feedback.get("severity") or "",
        "{{page_path}}": feedback.get("page_path") or "（未提供）",
        "{{title}}": feedback.get("title") or "",
        "{{description}}": feedback.get("description") or "",
        "{{attachments}}": attachment_text,
    }
    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)
    return prompt


_TOOL_VERBS = {
    "Read": "读取",
    "Edit": "修改",
    "Write": "新建",
    "NotebookEdit": "修改",
    "Grep": "搜索",
    "Glob": "查找文件",
    "Task": "启动子任务",
    "Agent": "启动子任务",
}


def describe_tool_use(block: dict) -> str | None:
    """把 claude stream-json 的 tool_use 块转写为一行中文动作。"""
    name = block.get("name") or ""
    tool_input = block.get("input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if name == "Bash":
        command = str(tool_input.get("command") or "").strip().replace("\n", " ")
        return f"执行命令：{command[:120]}" if command else "执行命令"
    if name in ("Read", "Edit", "Write"):
        target = tool_input.get("file_path")
    elif name == "NotebookEdit":
        target = tool_input.get("notebook_path")
    elif name in ("Grep", "Glob"):
        target = tool_input.get("pattern")
    else:
        target = None
    verb = _TOOL_VERBS.get(name)
    if verb and target:
        return f"{verb} {target}"
    if verb:
        return verb
    return f"使用工具 {name}" if name else None


def _parse_stream_line(line: str) -> dict | None:
    """解析一行 stream-json 事件；不关心的事件返回 None。"""
    text = (line or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    event_type = payload.get("type")
    if event_type == "assistant":
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return None
        return {
            "type": "assistant",
            "content": [b for b in content if isinstance(b, dict)],
        }
    if event_type == "result":
        return {
            "type": "result",
            "is_error": payload.get("is_error"),
            "result": payload.get("result"),
        }
    return None


def _kill_process_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        result = run_command(["taskkill", "/F", "/T", "/PID", str(proc.pid)], check=False)
        if result.returncode == 0:
            return
    proc.kill()


def invoke_claude(cfg: dict, worktree: Path, prompt: str, run_dir: Path,
                  on_action=None) -> dict:
    claude_cfg = cfg["claude"]
    parts = [claude_cfg["command"], "-p", "--output-format", "stream-json", "--verbose"]
    if claude_cfg["dangerously_skip_permissions"]:
        parts.append("--dangerously-skip-permissions")
    else:
        parts += ["--permission-mode", claude_cfg["permission_mode"]]
        if claude_cfg["allowed_tools"]:
            parts += ["--allowedTools", ",".join(claude_cfg["allowed_tools"])]
    log(f"调用代理: {' '.join(parts)}（超时 {claude_cfg['timeout_minutes']} 分钟）")

    timed_out = threading.Event()
    parsed: dict | None = None
    output_path = run_dir / "claude-output.txt"
    stderr_path = run_dir / "claude-stderr.txt"

    def kill_on_timeout() -> None:
        timed_out.set()
        _kill_process_tree(proc)

    with output_path.open("w", encoding="utf-8") as output_file, \
            stderr_path.open("w", encoding="utf-8") as stderr_file:
        proc = subprocess.Popen(
            parts,
            cwd=str(worktree),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        watchdog = threading.Timer(claude_cfg["timeout_minutes"] * 60, kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except OSError:
                pass  # stdin 提前断开（CLI 未读输入即退出），交由退出码/输出判定
            for line in proc.stdout:
                output_file.write(line)
                payload = _parse_stream_line(line)
                if payload is None:
                    continue
                if payload["type"] == "assistant":
                    for block in payload["content"]:
                        if block.get("type") == "tool_use":
                            action_text = describe_tool_use(block)
                            if action_text and on_action:
                                on_action(action_text)
                elif payload["type"] == "result":
                    parsed = {
                        "is_error": bool(payload.get("is_error")),
                        "result": str(payload.get("result") or ""),
                    }
            proc.wait()
        finally:
            watchdog.cancel()
            if proc.poll() is None:
                _kill_process_tree(proc)
                proc.wait()

    if timed_out.is_set():
        raise RunFailure(
            f"代理执行超时（>{claude_cfg['timeout_minutes']} 分钟），日志: {run_dir}"
        )
    if parsed is None:
        raise RunFailure(
            f"代理输出无法解析（退出码 {proc.returncode}），原始输出见 {output_path}"
        )
    return parsed


def run_gates(cfg: dict, worktree: Path, files: list[str], run_dir: Path,
              progress: ProgressReporter) -> str:
    repo_dir = Path(cfg["repo_dir"])
    checks: list[tuple[str, str, Path]] = []
    backend_command = cfg["gates"]["backend_command"].format(python=cfg["backend_python"])
    if any(path.startswith("backend/") for path in files):
        checks.append(("backend", backend_command, worktree / "backend"))
    if any(path.startswith("frontend/") for path in files):
        checks.append(("frontend", cfg["gates"]["frontend_command"], worktree / "frontend"))
    if not checks:
        raise RunFailure(f"改动不属于 backend/ 或 frontend/，无法执行门禁: {', '.join(files)}")

    timeout = cfg["gates"]["timeout_minutes"] * 60
    backend_env = {**os.environ, **load_env_values(repo_dir)}
    gate_lines: list[str] = []
    try:
        for name, command, cwd in checks:
            progress.stage(f"gate_{name}")
            if name == "frontend":
                ensure_node_modules(worktree, repo_dir)
            log(f"门禁执行 [{name}]: {command}")
            try:
                result = run_command(
                    command, cwd=cwd, shell=True, timeout=timeout,
                    env=backend_env if name == "backend" else None,
                )
            except subprocess.TimeoutExpired:
                gate_lines.append(f"[{name}] 超时（>{cfg['gates']['timeout_minutes']} 分钟）")
                raise RunFailure(f"门禁超时 [{name}]，日志: {run_dir}")
            gate_lines.append(f"[{name}] exit={result.returncode}")
            gate_lines.append((result.stdout or "")[-3000:])
            gate_lines.append((result.stderr or "")[-2000:])
            if result.returncode != 0:
                raise RunFailure(f"门禁失败 [{name}] exit={result.returncode}，日志: {run_dir}")
    finally:
        (run_dir / "gates.log").write_text("\n".join(gate_lines), encoding="utf-8")
        remove_node_modules_link(worktree)
    return "\n".join(gate_lines)


def commit_changes(worktree: Path, feedback: dict, base_sha: str) -> str:
    if changed_files(worktree):
        run_command(["git", "add", "-A"], cwd=worktree, check=True)
        message = f"fix(feedback#{feedback['id']}): {feedback.get('title') or ''}".strip()
        run_command(["git", "commit", "-m", message], cwd=worktree, check=True)
    result = run_command(
        ["git", "log", "--stat", "--oneline", f"{base_sha}..HEAD"],
        cwd=worktree, check=True,
    )
    return result.stdout


def compose_summary(parsed: dict, branch: str, diff_stat: str, gate_summary: str, run_dir: Path) -> str:
    agent_summary = (parsed.get("result") or "").strip()
    if len(agent_summary) > 1500:
        agent_summary = agent_summary[:1500] + "…"
    return (
        f"分支: {branch}\n"
        f"代理摘要:\n{agent_summary or '（代理未输出摘要）'}\n"
        f"改动统计:\n{diff_stat}\n"
        f"门禁结果:\n{gate_summary}\n"
        f"运行日志: {run_dir}"
    )


def process_feedback(cfg: dict, api: ApiClient, feedback: dict) -> None:
    feedback_id = feedback["id"]
    run_dir = RUNNER_DIR / "runs" / f"{feedback_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"开始处理反馈 #{feedback_id}: {feedback.get('title')}")
    progress = ProgressReporter(api, feedback_id)
    try:
        progress.stage("preparing")
        worktree, branch, base_sha = prepare_worktree(cfg, feedback)
        if feedback.get("attachments"):
            progress.stage("fetching")
        attachments = download_attachments(api, feedback, run_dir)
        prompt = build_prompt(feedback, attachments)
        (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")

        progress.stage("agent")
        parsed = invoke_claude(cfg, worktree, prompt, run_dir, on_action=progress.action)
        if parsed["is_error"]:
            raise RunFailure(f"代理执行报错: {parsed['result'][:500] or '未知错误'}")

        files = sorted(set(changed_files(worktree)) | set(committed_changes(worktree, base_sha)))
        if not files:
            raise RunFailure("代理未产生任何文件改动")
        blocked = sensitive_hits(cfg, files)
        if blocked:
            git(cfg, "worktree", "remove", "--force", str(worktree), check=False)
            git(cfg, "branch", "-D", branch, check=False)
            raise RunFailure(f"改动触碰敏感文件，已阻断并删除分支: {', '.join(blocked)}")

        gate_summary = run_gates(cfg, worktree, files, run_dir, progress)

        progress.stage("committing")
        commit_stat = commit_changes(worktree, feedback, base_sha)
        (run_dir / "diff-stat.txt").write_text(commit_stat, encoding="utf-8")

        summary = compose_summary(parsed, branch, commit_stat, gate_summary, run_dir)
        try:
            api.finish(feedback_id, True, branch=branch, summary=summary)
        except Exception as exc:
            raise RunFailure(
                f"实现已完成（分支 {branch} 已保留，请人工审核），但结果回写失败: {exc}"
            )
        log(f"反馈 #{feedback_id} 实现完成: {branch}")
    except Exception as exc:
        log(f"反馈 #{feedback_id} 处理失败: {exc}")
        try:
            api.finish(feedback_id, False, error=f"{exc}\n运行日志: {run_dir}")
        except Exception as finish_exc:
            log(f"回写失败原因也失败（反馈停留在 running，可人工重新排队）: {finish_exc}")


def cleanup_merged(cfg: dict) -> None:
    worktrees_dir = Path(cfg["worktrees_dir"])
    if not worktrees_dir.exists():
        log("worktrees 目录不存在，无需清理")
        return
    base = resolve_base_branch(cfg)
    merged_output = git(cfg, "branch", "--merged", base, check=False).stdout or ""
    merged_branches = {
        line.strip().lstrip("* ").strip()
        for line in merged_output.splitlines()
        if line.strip()
    }
    for worktree in sorted(worktrees_dir.glob("fb-*")):
        match = re.fullmatch(r"fb-(\d+)", worktree.name)
        if not match:
            continue
        branch = f"ai-feedback/{match.group(1)}"
        if branch not in merged_branches:
            log(f"保留未合入分支 {branch}")
            continue
        remove_node_modules_link(worktree)
        git(cfg, "worktree", "remove", "--force", str(worktree), check=False)
        git(cfg, "branch", "-d", branch, check=False)
        log(f"已清理 {branch}")


def handle_sigint(signum, frame) -> None:
    if STOP["requested"]:
        log("强制退出")
        release_lock()
        os._exit(130)
    STOP["requested"] = True
    log("收到中断，完成当前任务后退出（再按一次 Ctrl+C 强制退出）")


def main() -> None:
    parser = argparse.ArgumentParser(description="问题反馈 AI 自动实现 Runner")
    parser.add_argument("--config", default=str(RUNNER_DIR / "config.local.json"))
    parser.add_argument("--once", action="store_true", help="处理完当前队列后退出")
    parser.add_argument("--cleanup", action="store_true", help="清理已合入的 worktree 与分支")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_sigint)
    cfg = load_config(Path(args.config))
    acquire_lock()
    api = ApiClient(cfg["base_url"], cfg["username"], cfg["password"])
    try:
        if args.cleanup:
            cleanup_merged(cfg)
            return
        log(
            f"Runner 启动: {cfg['base_url']}，长轮询等待（超时 {WAIT_TIMEOUT_SECONDS}s，"
            f"出错退避 {cfg['poll_interval_seconds']}s）"
        )
        while not STOP["requested"]:
            try:
                ids = api.wait_queued(2 if args.once else WAIT_TIMEOUT_SECONDS)
            except Exception as exc:
                log(f"等待队列失败: {exc}")
                wait_for(cfg["poll_interval_seconds"])
                continue
            if not ids:
                if args.once:
                    log("队列为空，退出（--once）")
                    return
                continue
            for feedback_id in ids:
                if STOP["requested"]:
                    break
                try:
                    claimed = api.claim(feedback_id)
                except Exception as exc:
                    log(f"认领反馈 #{feedback_id} 失败: {exc}")
                    claimed = None
                if not claimed:
                    continue
                process_feedback(cfg, api, claimed)
        log("Runner 已停止")
    finally:
        api.close()
        release_lock()


if __name__ == "__main__":
    main()
