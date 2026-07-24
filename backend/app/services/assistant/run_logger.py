"""结构化 Agent 运行日志 — JSONL 异步写入"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_LOG_ROOT = "logs/assistant"
LOG_RETENTION_DAYS = 30


def _safe_json_default(obj: Any) -> Any:
    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


class RunLogger:
    def __init__(
        self,
        trace_id: str,
        session_id: str = "",
        user_id: str = "",
        log_root: Optional[str] = None,
    ):
        from app.core.config import get_settings

        settings = get_settings()
        self.trace_id = trace_id
        self.session_id = session_id
        self.user_id = user_id
        self._log_root = Path(
            log_root
            or os.environ.get("AI_RUN_LOG_DIR")
            or (Path(__file__).resolve().parents[3] / DEFAULT_LOG_ROOT)
        )
        self._lock = asyncio.Lock()
        self._file_path: Optional[Path] = None
        self._opened = False
        self._closed = False
        self._write_tasks: list[asyncio.Task] = []
        self._settings = settings

    def _resolve_file_path(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dir_path = self._log_root / day
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / f"{self.trace_id}.jsonl"

    def _ensure_opened_sync(self) -> Path:
        if self._file_path is None:
            self._file_path = self._resolve_file_path()
        return self._file_path

    async def _open(self) -> None:
        async with self._lock:
            if self._opened:
                return
            self._file_path = self._resolve_file_path()
            self._file_path.touch(exist_ok=True)
            self._opened = True
            logger.debug(f"[run_logger] opened: {self._file_path}")

    async def log(self, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self._closed:
            return
        if not self._opened:
            await self._open()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "event": event,
            "data": data or {},
        }
        try:
            line = json.dumps(record, ensure_ascii=False, default=_safe_json_default)
        except Exception as e:
            line = json.dumps(
                {
                    "ts": record["ts"],
                    "trace_id": self.trace_id,
                    "event": "log_error",
                    "data": {"original_event": event, "error": str(e)},
                },
                ensure_ascii=False,
            )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._append_line, line)

    def _append_line(self, line: str) -> None:
        if self._file_path is None:
            return
        with open(self._file_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            self._opened = False


def list_log_files(
    log_root: Optional[Path] = None,
    date: Optional[str] = None,
    session_id: Optional[str] = None,
) -> list[Path]:
    if log_root is None:
        log_root = Path(
            os.environ.get("AI_RUN_LOG_DIR")
            or (Path(__file__).resolve().parents[3] / DEFAULT_LOG_ROOT)
        )
    if not log_root.exists():
        return []
    results: list[Path] = []
    if date:
        day_dirs = [log_root / date]
    else:
        day_dirs = sorted(
            [p for p in log_root.iterdir() if p.is_dir()],
            reverse=True,
        )
    for day_dir in day_dirs:
        if not day_dir.exists():
            continue
        for fp in day_dir.glob("*.jsonl"):
            if session_id:
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        first_line = f.readline()
                        if session_id not in first_line:
                            continue
                except Exception:
                    continue
            results.append(fp)
    return results


def read_log_file(path: Path) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    records: list[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


async def cleanup_old_logs(
    log_root: Optional[Path] = None,
    retention_days: int = LOG_RETENTION_DAYS,
) -> int:
    if log_root is None:
        log_root = Path(
            os.environ.get("AI_RUN_LOG_DIR")
            or (Path(__file__).resolve().parents[3] / DEFAULT_LOG_ROOT)
        )
    if not log_root.exists():
        return 0
    now = time.time()
    removed = 0
    for day_dir in log_root.iterdir():
        if not day_dir.is_dir():
            continue
        try:
            dir_mtime = day_dir.stat().st_mtime
        except Exception:
            continue
        age_days = (now - dir_mtime) / 86400
        if age_days > retention_days:
            try:
                for fp in day_dir.glob("*.jsonl"):
                    fp.unlink()
                day_dir.rmdir()
                removed += 1
            except Exception as e:
                logger.warning(f"[run_logger] cleanup failed for {day_dir}: {e}")
    return removed
