"""问题反馈 AI 自动实现 Runner。

轮询后端问题反馈队列（ai_status=queued），认领后：
1. 在独立 git worktree + ai-feedback/<id> 分支上运行 claude CLI 修改代码；
2. 按改动范围执行门禁（backend pytest / frontend build / 敏感文件扫描）；
3. 通过后本地提交并回写反馈结果（ai-finish），失败则回写失败原因。

设计与约定见 docs/superpowers/specs/2026-09-29-feedback-ai-autofix-design.md。
运行：<python.exe> runner.py [--config config.local.json] [--once] [--cleanup]
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx

RUNNER_DIR = Path(__file__).resolve().parent
REPO_DIR_DEFAULT = RUNNER_DIR.parents[1]
LOCK_FILE = RUNNER_DIR / ".runner.lock"
STOP = {"requested": False}


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


class RunFailure(Exception):
    """单条反馈处理失败（原因会回写到反馈单）。"""


def run_command(cmd, cwd=None, timeout=None, check=False, shell=False, input_text=None):
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=shell,
        input=input_text,
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
    cfg.setdefault("gates", {})
    cfg["gates"].setdefault("backend_command", "{python} -m pytest -q")
    cfg["gates"].setdefault("frontend_command", "npm run build")
    cfg["gates"].setdefault("timeout_minutes", 30)
    cfg.setdefault("claude", {})
    cfg["claude"].setdefault("command", "claude")
    cfg["claude"].setdefault("timeout_minutes", 60)
    cfg["claude"].setdefault("allowed_tools", [
        "Read", "Edit", "Write", "Glob", "Grep",
        "Bash(python:*)", "Bash(npm:*)", "Bash(npx:*)",
        "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
    ])
    cfg.setdefault("blocked_globs", [
        ".env", ".env.*", "**/.env", "**/.env.*",
        "scripts/deploy-*", "docker-compose-prod.yml",
    ])
    return cfg


class ApiClient:
    """后端 API 客户端：登录、拉队列、认领、回写。"""

    def __init__(self, base_url: str, username: str, password: str):
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=30)
        self._username = username
        self._password = password
        self._token: str | None = None

    def _login(self) -> None:
        response = self._client.post(
            "/api/v1/basicdata/auth/login",
            data={"username": self._username, "password": self._password, "login_type": "employee"},
        )
        body = response.json()
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

    def list_queued(self, page_size: int = 10) -> list[dict]:
        response = self._request("GET", "/api/v1/basicdata/feedback", params={
            "ai_status": "queued",
            "page": 1,
            "page_size": page_size,
            "sort_by": "created_at",
            "sort_order": "asc",
        })
        body = response.json()
        if body.get("code") != 0:
            raise RuntimeError(f"拉取队列失败: {body.get('message')}")
        return body["data"]["items"]

    def claim(self, feedback_id: int) -> dict | None:
        response = self._request("POST", f"/api/v1/basicdata/feedback/{feedback_id}/ai-claim")
        if response.status_code == 409:
            return None
        body = response.json()
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
        body = response.json()
        if body.get("code") != 0:
            raise RuntimeError(f"回写结果失败: {body.get('message')}")

    def get_bytes(self, url: str) -> bytes:
        response = self._request("GET", url)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        return response.content

    def close(self) -> None:
        self._client.close()


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
    result = run_command(["git", "status", "--porcelain"], cwd=worktree, check=True)
    files: list[str] = []
    for line in (result.stdout or "").splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip('"').replace("\\", "/"))
    return files


def sensitive_hits(cfg: dict, files: list[str]) -> list[str]:
    hits: list[str] = []
    for path in files:
        for pattern in cfg["blocked_globs"]:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch("/" + path, "/" + pattern):
                hits.append(path)
                break
    return hits


def prepare_worktree(cfg: dict, feedback: dict) -> tuple[Path, str]:
    feedback_id = feedback["id"]
    worktrees_dir = Path(cfg["worktrees_dir"])
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    worktree = worktrees_dir / f"fb-{feedback_id}"
    branch = f"ai-feedback/{feedback_id}"
    if worktree.exists():
        git(cfg, "worktree", "remove", "--force", str(worktree), check=False)
    git(cfg, "worktree", "prune", check=False)
    git(cfg, "branch", "-D", branch, check=False)
    git(cfg, "worktree", "add", "-b", branch, str(worktree), cfg["base_branch"], check=True)
    log(f"worktree 就绪: {worktree}（分支 {branch}）")
    return worktree, branch


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


def parse_claude_output(stdout: str) -> dict | None:
    text = (stdout or "").strip()
    if not text:
        return None
    payload = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                payload = None
    if not isinstance(payload, dict):
        return None
    return {
        "is_error": bool(payload.get("is_error")),
        "result": str(payload.get("result") or ""),
    }


def invoke_claude(cfg: dict, worktree: Path, prompt: str, run_dir: Path) -> dict:
    claude_cfg = cfg["claude"]
    parts = [
        claude_cfg["command"],
        "-p",
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
    ]
    if claude_cfg["allowed_tools"]:
        parts += ["--allowedTools", ",".join(claude_cfg["allowed_tools"])]
    command_line = " ".join(parts)
    log(f"调用代理: {command_line}（超时 {claude_cfg['timeout_minutes']} 分钟）")
    try:
        result = run_command(
            command_line, cwd=worktree, shell=True, input_text=prompt,
            timeout=claude_cfg["timeout_minutes"] * 60,
        )
    except subprocess.TimeoutExpired:
        raise RunFailure(f"代理执行超时（>{claude_cfg['timeout_minutes']} 分钟）")
    (run_dir / "claude-output.txt").write_text(result.stdout or "", encoding="utf-8")
    if result.stderr:
        (run_dir / "claude-stderr.txt").write_text(result.stderr, encoding="utf-8")
    parsed = parse_claude_output(result.stdout or "")
    if parsed is None:
        raise RunFailure(
            f"代理输出无法解析（退出码 {result.returncode}），原始输出见 {run_dir / 'claude-output.txt'}"
        )
    return parsed


def run_gates(cfg: dict, worktree: Path, files: list[str], run_dir: Path) -> str:
    checks: list[tuple[str, str, Path]] = []
    backend_command = cfg["gates"]["backend_command"].format(python=cfg["backend_python"])
    if any(path.startswith("backend/") for path in files):
        checks.append(("backend", backend_command, worktree / "backend"))
    if any(path.startswith("frontend/") for path in files):
        checks.append(("frontend", cfg["gates"]["frontend_command"], worktree / "frontend"))
    if not checks:
        raise RunFailure(f"改动不属于 backend/ 或 frontend/，无法执行门禁: {', '.join(files)}")

    timeout = cfg["gates"]["timeout_minutes"] * 60
    gate_lines: list[str] = []
    for name, command, cwd in checks:
        log(f"门禁执行 [{name}]: {command}")
        try:
            result = run_command(command, cwd=cwd, shell=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            gate_lines.append(f"[{name}] 超时（>{cfg['gates']['timeout_minutes']} 分钟）")
            (run_dir / "gates.log").write_text("\n".join(gate_lines), encoding="utf-8")
            raise RunFailure(f"门禁超时 [{name}]，日志: {run_dir}")
        gate_lines.append(f"[{name}] exit={result.returncode}")
        gate_lines.append((result.stdout or "")[-3000:])
        gate_lines.append((result.stderr or "")[-2000:])
        if result.returncode != 0:
            (run_dir / "gates.log").write_text("\n".join(gate_lines), encoding="utf-8")
            raise RunFailure(f"门禁失败 [{name}] exit={result.returncode}，日志: {run_dir}")
    return "\n".join(gate_lines)


def commit_changes(worktree: Path, feedback: dict) -> str:
    run_command(["git", "add", "-A"], cwd=worktree, check=True)
    message = f"fix(feedback#{feedback['id']}): {feedback.get('title') or ''}".strip()
    run_command(["git", "commit", "-m", message], cwd=worktree, check=True)
    result = run_command(["git", "show", "--stat", "--oneline", "HEAD"], cwd=worktree, check=True)
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
    try:
        worktree, branch = prepare_worktree(cfg, feedback)
        attachments = download_attachments(api, feedback, run_dir)
        prompt = build_prompt(feedback, attachments)
        (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")

        parsed = invoke_claude(cfg, worktree, prompt, run_dir)
        if parsed["is_error"]:
            raise RunFailure(f"代理执行报错: {parsed['result'][:500] or '未知错误'}")

        files = changed_files(worktree)
        if not files:
            raise RunFailure("代理未产生任何文件改动")
        blocked = sensitive_hits(cfg, files)
        if blocked:
            raise RunFailure(f"改动触碰敏感文件，已阻断: {', '.join(blocked)}")

        gate_summary = run_gates(cfg, worktree, files, run_dir)
        (run_dir / "gates.log").write_text(gate_summary, encoding="utf-8")

        commit_stat = commit_changes(worktree, feedback)
        (run_dir / "diff-stat.txt").write_text(commit_stat, encoding="utf-8")

        summary = compose_summary(parsed, branch, commit_stat, gate_summary, run_dir)
        api.finish(feedback_id, True, branch=branch, summary=summary)
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
    for worktree in sorted(worktrees_dir.glob("fb-*")):
        match = re.fullmatch(r"fb-(\d+)", worktree.name)
        if not match:
            continue
        branch = f"ai-feedback/{match.group(1)}"
        if branch not in merged_output:
            log(f"保留未合入分支 {branch}")
            continue
        git(cfg, "worktree", "remove", "--force", str(worktree), check=False)
        git(cfg, "branch", "-d", branch, check=False)
        log(f"已清理 {branch}")


def handle_sigint(signum, frame) -> None:
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
        log(f"Runner 启动: {cfg['base_url']}，轮询间隔 {cfg['poll_interval_seconds']}s")
        while not STOP["requested"]:
            try:
                items = api.list_queued(page_size=10)
            except Exception as exc:
                log(f"拉取队列失败: {exc}")
                time.sleep(cfg["poll_interval_seconds"])
                continue
            if not items:
                if args.once:
                    log("队列为空，退出（--once）")
                    return
                time.sleep(cfg["poll_interval_seconds"])
                continue
            for item in items:
                if STOP["requested"]:
                    break
                try:
                    claimed = api.claim(item["id"])
                except Exception as exc:
                    log(f"认领反馈 #{item['id']} 失败: {exc}")
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
