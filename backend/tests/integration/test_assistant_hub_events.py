"""智能助手 assistant-events 上报接线集成测试：会话开始/消息/回复/异常/会话结束。

Provider 默认 rule_based（无真实 LLM 调用），仅验证上报点接线与 payload 关键字段。
"""

import asyncio
import json

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.basicdata.ai_agent import AssistantRun
from app.services.assistant import hub_reporter
from tests.conftest import login


@pytest.fixture
def hub_capture(monkeypatch):
    """启用上报并把 _post 换成内存捕获，测完恢复设置。"""
    settings = get_settings()
    saved = (settings.AEOS_HUB_BASE, settings.AEOS_SYSTEM_ID, settings.AEOS_SYSTEM_TOKEN)
    settings.AEOS_HUB_BASE = "http://hub-mock"
    settings.AEOS_SYSTEM_ID = "中台智能助手"
    settings.AEOS_SYSTEM_TOKEN = "test-token"
    captured = []

    async def _stub(payload):
        captured.append(payload)

    monkeypatch.setattr(hub_reporter, "_post", _stub)
    yield captured
    settings.AEOS_HUB_BASE, settings.AEOS_SYSTEM_ID, settings.AEOS_SYSTEM_TOKEN = saved


async def _flush(captured, count):
    for _ in range(50):
        if len(captured) >= count:
            return
        await asyncio.sleep(0.01)


async def _wait_run_row(trace_id: str) -> None:
    """等流式请求被 shield 的落库任务提交（否则其事务会与下一用例的 TRUNCATE 抢锁）。"""
    for _ in range(100):
        async with AsyncSessionLocal() as session:
            row = (await session.execute(
                select(AssistantRun.id).where(AssistantRun.trace_id == trace_id)
            )).first()
        if row:
            return
        await asyncio.sleep(0.05)


async def test_chat_reports_conversation_message_reply(client, hub_capture):
    headers = await login(client, "admin")
    r = await client.post("/api/v1/assistant/chat", json={"message": "你好"}, headers=headers)
    assert r.status_code == 200
    assert r.json().get("code") == 0
    await _flush(hub_capture, 3)

    events = {p["event"] for p in hub_capture}
    assert {"conversation_started", "message", "assistant_reply"} <= events

    started = next(p for p in hub_capture if p["event"] == "conversation_started")
    assert started["traceId"] == r.json()["data"]["session_id"]
    assert started["detail"]["userId"] == "1"

    message = next(p for p in hub_capture if p["event"] == "message")
    assert "用户询问" in message["summary"] and "你好" in message["summary"]

    reply = next(p for p in hub_capture if p["event"] == "assistant_reply")
    assert reply["status"] == "completed"
    assert reply["durationMs"] is not None


async def test_same_session_no_duplicate_conversation_started(client, hub_capture):
    headers = await login(client, "admin")
    r1 = await client.post("/api/v1/assistant/chat", json={"message": "你好"}, headers=headers)
    session_id = r1.json()["data"]["session_id"]
    await _flush(hub_capture, 3)

    await client.post("/api/v1/assistant/chat", json={"message": "继续", "session_id": session_id}, headers=headers)
    await _flush(hub_capture, 6)

    started_count = sum(1 for p in hub_capture if p["event"] == "conversation_started")
    assert started_count == 1
    assert all(p["traceId"] == session_id for p in hub_capture)


async def test_stream_error_reported(client, hub_capture):
    headers = await login(client, "admin")
    body = ""
    async with client.stream(
        "POST", "/api/v1/assistant/chat/stream", json={"message": "你好"}, headers=headers
    ) as resp:
        async for chunk in resp.aiter_text():
            body += chunk
    await _flush(hub_capture, 3)

    events = [p["event"] for p in hub_capture]
    assert "conversation_started" in events and "message" in events
    assert "error" in events
    assert "assistant_reply" not in events

    trace_id = None
    for line in body.split("\n"):
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            if payload.get("trace_id"):
                trace_id = payload["trace_id"]
    assert trace_id
    await _wait_run_row(trace_id)


async def test_clear_session_reports_ended(client, hub_capture):
    headers = await login(client, "admin")
    r = await client.delete("/api/v1/assistant/sessions/sess-xyz", headers=headers)
    assert r.json().get("code") == 0
    await _flush(hub_capture, 1)

    ended = hub_capture[0]
    assert ended["event"] == "conversation_ended"
    assert ended["traceId"] == "sess-xyz"
