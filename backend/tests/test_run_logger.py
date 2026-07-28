"""run_logger 单元测试"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from app.services.assistant.run_logger import RunLogger, list_log_files, read_log_file, cleanup_old_logs


@pytest.mark.asyncio
async def test_run_logger_writes_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        logger = RunLogger(trace_id="abc123", session_id="s1", user_id="u1", log_root=tmp)
        await logger.log("request", {"message": "hello"})
        await logger.log("intent_done", {"intent": "QUERY_DATA"})
        await logger.close()

        files = list(Path(tmp).rglob("*.jsonl"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.strip()]
        assert len(lines) == 2

        r1 = json.loads(lines[0])
        assert r1["trace_id"] == "abc123"
        assert r1["session_id"] == "s1"
        assert r1["user_id"] == "u1"
        assert r1["event"] == "request"
        assert r1["data"]["message"] == "hello"

        r2 = json.loads(lines[1])
        assert r2["event"] == "intent_done"


@pytest.mark.asyncio
async def test_run_logger_unserializable_data_does_not_crash():
    with tempfile.TemporaryDirectory() as tmp:
        logger = RunLogger(trace_id="xyz", log_root=tmp)
        await logger.log("weird", {"obj": object()})
        await logger.close()
        files = list(Path(tmp).rglob("*.jsonl"))
        assert len(files) == 1
        lines = [l for l in files[0].read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1


@pytest.mark.asyncio
async def test_list_log_files_filter_by_session():
    with tempfile.TemporaryDirectory() as tmp:
        l1 = RunLogger(trace_id="t1", session_id="sess-A", log_root=tmp)
        l2 = RunLogger(trace_id="t2", session_id="sess-B", log_root=tmp)
        await l1.log("x", {"a": 1})
        await l2.log("x", {"b": 2})
        await l1.close()
        await l2.close()

        files = list_log_files(log_root=Path(tmp), session_id="sess-A")
        assert len(files) == 1
        assert files[0].stem == "t1"


def test_read_log_file():
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / "test.jsonl"
        fp.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
        records = read_log_file(fp)
        assert len(records) == 2
        assert records[0]["a"] == 1


@pytest.mark.asyncio
async def test_cleanup_old_logs_removes_old_dirs():
    import time as time_mod

    with tempfile.TemporaryDirectory() as tmp:
        old_dir = Path(tmp) / "2020-01-01"
        old_dir.mkdir()
        (old_dir / "old.jsonl").write_text("{}", encoding="utf-8")
        os.utime(old_dir, (1577836800, 1577836800))

        removed = await cleanup_old_logs(log_root=Path(tmp), retention_days=30)
        assert removed == 1
        assert not old_dir.exists()
