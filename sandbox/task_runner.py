"""One-shot task runner used by the per-task Docker sandbox container."""

import asyncio
import base64
import json
import sys

from fastapi import HTTPException

from app import run_task


def _error(message: str) -> dict:
    return {
        "ok": False,
        "exit_code": None,
        "stdout": "",
        "stderr": message[:1000],
        "duration_ms": 0,
        "truncated": False,
    }


def main() -> None:
    try:
        payload = json.loads(sys.stdin.readline())
        package = base64.b64decode(payload.get("package_b64") or "")
        result = asyncio.run(run_task(
            package,
            str(payload.get("script") or ""),
            payload.get("params") if isinstance(payload.get("params"), dict) else {},
            payload.get("args") if isinstance(payload.get("args"), list) else [],
            payload.get("input_files") if isinstance(payload.get("input_files"), dict) else {},
            int(payload.get("timeout_s") or 30),
        ))
    except HTTPException as exc:
        result = _error(str(exc.detail))
    except Exception as exc:
        result = _error(f"{type(exc).__name__}: {exc}")
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
