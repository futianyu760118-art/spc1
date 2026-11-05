"""Task-level Docker sandbox orchestrator.

The backend sends one skill task. This service starts one disposable container
with the sandbox image, pipes the task JSON through stdin, returns the runner's
JSON result, and removes the container.
"""

import asyncio
import base64
import hmac
import json
import logging
import os
import socket
import uuid

import docker
from docker.errors import DockerException, ImageNotFound
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

TOKEN = (os.environ.get("SANDBOX_ORCHESTRATOR_TOKEN") or os.environ.get("SKILL_SANDBOX_TOKEN") or "").strip()
IMAGE = os.environ.get("SANDBOX_IMAGE", "spc-v2-sandbox:latest").strip()
RUNTIME = (os.environ.get("SANDBOX_RUNTIME", "runc") or "runc").strip()
TASK_NETWORK = (os.environ.get("SANDBOX_TASK_NETWORK", "none") or "none").strip()
MAX_CONCURRENCY = max(1, int(os.environ.get("SANDBOX_MAX_CONCURRENCY", "2") or 2))
DEP_INSTALL_TIMEOUT_S = max(10, int(os.environ.get("SANDBOX_DEP_INSTALL_TIMEOUT_S", "60") or 60))
KEEP_TASK_CONTAINERS = os.environ.get("SANDBOX_KEEP_TASK_CONTAINERS", "").strip().lower() in ("1", "true", "yes")
MAX_PACKAGE_BYTES = 20 * 1024 * 1024
MAX_WAIT_S = 300

app = FastAPI(title="SPC Sandbox Orchestrator", docs_url=None, redoc_url=None, openapi_url=None)
_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)


class RunRequest(BaseModel):
    package_b64: str
    script: str
    params: dict = Field(default_factory=dict)
    args: list[str] = Field(default_factory=list)
    input_files: dict[str, str] = Field(default_factory=dict)
    timeout_s: int = 30
    user_id: str = ""


def _check_token(token: str | None) -> None:
    if not TOKEN:
        raise HTTPException(status_code=503, detail="sandbox orchestrator token not configured")
    if not token or not hmac.compare_digest(token, TOKEN):
        raise HTTPException(status_code=401, detail="invalid sandbox token")


def _container_task(payload: dict, timeout_s: int) -> dict:
    task_id = uuid.uuid4().hex
    wait_s = min(MAX_WAIT_S, max(60, int(timeout_s or 30) + DEP_INSTALL_TIMEOUT_S + 30))
    client = docker.from_env()
    container = None
    try:
        container_name = f"spc-sandbox-task-{task_id[:12]}"
        container = client.containers.create(
            IMAGE,
            name=container_name,
            command=["python", "/app/task_runner.py"],
            stdin_open=True,
            detach=True,
            network_mode=TASK_NETWORK,
            read_only=True,
            user="10001:10001",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=128,
            mem_limit="512m",
            nano_cpus=1_000_000_000,
            runtime=RUNTIME,
            tmpfs={
                "/work": "size=128m,mode=1777,exec,nosuid,nodev",
                "/tmp": "size=32m,mode=1777,nosuid,nodev",
            },
            environment={"SANDBOX_DEP_INSTALL_TIMEOUT_S": str(DEP_INSTALL_TIMEOUT_S)},
            labels={"spc.sandbox.task": task_id},
            auto_remove=False,
        )
        container.start()
        logger.info("[sandbox] task=%s container=%s started", task_id, container.short_id)
        task_stream = container.attach_socket(params={"stdin": 1, "stream": 1})
        try:
            task_stream._sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            try:
                task_stream._sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        finally:
            task_stream.close()

        timed_out = False
        try:
            container.wait(timeout=wait_s)
        except Exception:
            timed_out = True
            try:
                container.kill()
            except Exception:
                pass
            try:
                container.wait(timeout=10)
            except Exception:
                pass

        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        if timed_out:
            return {
                "ok": False,
                "exit_code": None,
                "stdout": stdout[-4000:],
                "stderr": f"task timeout after {wait_s}s",
                "duration_ms": None,
                "truncated": False,
            }
        try:
            parsed = json.loads(stdout.strip())
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
        return {
            "ok": False,
            "exit_code": None,
            "stdout": stdout[-4000:],
            "stderr": (stderr or "invalid task runner output")[-4000:],
            "duration_ms": None,
            "truncated": False,
        }
    finally:
        if container is not None:
            if KEEP_TASK_CONTAINERS:
                logger.info("[sandbox] task=%s container=%s retained for debugging", task_id, container.short_id)
            else:
                try:
                    container.remove(force=True)
                except Exception:
                    logger.warning("[sandbox] failed to remove task container %s", task_id)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "token_configured": bool(TOKEN),
        "image": IMAGE,
        "runtime": RUNTIME,
        "network": TASK_NETWORK,
        "max_concurrency": MAX_CONCURRENCY,
    }


@app.post("/run")
async def run(
    body: RunRequest,
    x_sandbox_token: str | None = Header(default=None),
) -> dict:
    _check_token(x_sandbox_token)
    try:
        package = base64.b64decode(body.package_b64, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="invalid package_base64")
    if not package or len(package) > MAX_PACKAGE_BYTES:
        raise HTTPException(status_code=413, detail="package too large or empty")

    try:
        await asyncio.wait_for(_semaphore.acquire(), timeout=1)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=429, detail="sandbox busy")
    try:
        payload = {
            "package_b64": body.package_b64,
            "script": body.script,
            "params": body.params,
            "args": body.args,
            "input_files": body.input_files,
            "timeout_s": max(1, min(int(body.timeout_s or 30), 60)),
        }
        logger.info(
            "[sandbox] task user=%s script=%s bytes=%s",
            body.user_id or "-", body.script, len(package),
        )
        try:
            return await asyncio.to_thread(_container_task, payload, body.timeout_s)
        except ImageNotFound as exc:
            logger.error("[sandbox] image %s not found: %s", IMAGE, exc)
            raise HTTPException(status_code=503, detail=f"sandbox image not found: {IMAGE}")
        except DockerException as exc:
            logger.error("[sandbox] docker error: %s", exc)
            raise HTTPException(status_code=502, detail=f"sandbox docker error: {str(exc)[:300]}")
    finally:
        _semaphore.release()
