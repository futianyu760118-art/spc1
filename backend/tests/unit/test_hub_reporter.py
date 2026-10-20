"""hub_reporter 单元测试：停用开关、payload 构造、请求头编码、失败吞掉。"""

import asyncio
import json

import pytest

from app.core.config import get_settings
from app.services.assistant import hub_reporter
from app.services.ai.base import TokenUsage


@pytest.fixture
def settings_fixture():
    settings = get_settings()
    saved = (
        settings.AEOS_HUB_BASE,
        settings.AEOS_SYSTEM_ID,
        settings.AEOS_SYSTEM_TOKEN,
        settings.AEOS_HUB_CA_CERT,
    )
    yield settings
    (
        settings.AEOS_HUB_BASE,
        settings.AEOS_SYSTEM_ID,
        settings.AEOS_SYSTEM_TOKEN,
        settings.AEOS_HUB_CA_CERT,
    ) = saved


def _enable(settings, hub_base="http://127.0.0.1:1"):
    settings.AEOS_HUB_BASE = hub_base
    settings.AEOS_SYSTEM_ID = "中台智能助手"
    settings.AEOS_SYSTEM_TOKEN = "test-token"


async def test_disabled_skips_report(settings_fixture, monkeypatch):
    captured = []

    async def _stub(payload):
        captured.append(payload)

    monkeypatch.setattr(hub_reporter, "_post", _stub)
    hub_reporter.report_assistant_event("s1", "message", "用户消息", summary="hi")
    await asyncio.sleep(0.01)
    assert captured == []


async def test_enabled_reports_fire_and_forget(settings_fixture, monkeypatch):
    _enable(settings_fixture)
    captured = []

    async def _stub(payload):
        captured.append(payload)

    monkeypatch.setattr(hub_reporter, "_post", _stub)
    hub_reporter.report_assistant_event(
        "s1", "message", "用户消息", status="info", summary="hello",
        detail={"length": 5}, started_at="2026-10-19T00:00:00+00:00", duration_ms=12.345,
    )
    await asyncio.sleep(0.01)
    assert len(captured) == 1
    payload = captured[0]
    assert payload["traceId"] == "s1"
    assert payload["event"] == "message"
    assert payload["eventId"].startswith("s1-message-")
    assert payload["status"] == "info"
    assert payload["summary"] == "hello"
    assert payload["detail"] == {"length": 5}
    assert payload["startedAt"] == "2026-10-19T00:00:00+00:00"
    assert payload["durationMs"] == 12.35
    assert "endedAt" not in payload
    assert "usage" not in payload


async def test_truncates_and_unique_event_ids(settings_fixture, monkeypatch):
    _enable(settings_fixture)
    captured = []

    async def _stub(payload):
        captured.append(payload)

    monkeypatch.setattr(hub_reporter, "_post", _stub)
    hub_reporter.report_assistant_event("s1", "note", "N" * 200, summary="S" * 900)
    hub_reporter.report_assistant_event("s1", "note", "x", summary="y")
    await asyncio.sleep(0.01)
    assert len(captured) == 2
    assert len(captured[0]["name"]) == 100
    assert len(captured[0]["summary"]) == 500
    assert captured[0]["eventId"] != captured[1]["eventId"]


def test_build_usage():
    assert hub_reporter.build_usage("rule_based", None) == {"modelId": "rule_based"}
    assert hub_reporter.build_usage("openai", "gpt-custom") == {"modelId": "gpt-custom"}
    usage = hub_reporter.build_usage("openai", None, TokenUsage(prompt_tokens=10, completion_tokens=4))
    assert usage == {"modelId": get_settings().AI_OPENAI_MODEL, "tokensIn": 10, "cachedTokens": 0, "tokensOut": 4}
    cached = hub_reporter.build_usage(
        "openai", None, TokenUsage(prompt_tokens=1200, completion_tokens=180, cached_tokens=800)
    )
    assert cached == {"modelId": get_settings().AI_OPENAI_MODEL, "tokensIn": 1200, "cachedTokens": 800, "tokensOut": 180}


async def test_report_model_call_skips_rule_based(settings_fixture, monkeypatch):
    _enable(settings_fixture)
    captured = []

    async def _stub(payload):
        captured.append(payload)

    monkeypatch.setattr(hub_reporter, "_post", _stub)
    hub_reporter.report_model_call("s1", "意图识别", provider="rule_based")
    await asyncio.sleep(0.01)
    assert captured == []


async def test_post_sends_encoded_headers_and_body(settings_fixture):
    received = []

    async def handler(reader, writer):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = await reader.read(4096)
            if not chunk:
                break
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        head_text = head.decode("utf-8", "replace")
        length = 0
        for line in head_text.split("\r\n")[1:]:
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
        while len(body) < length:
            body += await reader.read(4096)
        received.append({"head": head_text, "body": json.loads(body[:length])})
        resp = b"HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"
        writer.write(resp)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        _enable(settings_fixture, hub_base=f"http://127.0.0.1:{port}")
        await hub_reporter._post({"traceId": "s1", "event": "message", "eventId": "e1"})
    finally:
        server.close()
        await server.wait_closed()

    assert len(received) == 1
    head = received[0]["head"]
    assert "x-aeos-system-id: %E4%B8%AD%E5%8F%B0%E6%99%BA%E8%83%BD%E5%8A%A9%E6%89%8B" in head
    assert "x-aeos-system-token: test-token" in head
    assert received[0]["body"] == {"traceId": "s1", "event": "message", "eventId": "e1"}


async def test_post_swallows_connection_error(settings_fixture):
    _enable(settings_fixture, hub_base="http://127.0.0.1:1")
    await hub_reporter._post({"traceId": "s1", "event": "message", "eventId": "e1"})


async def test_get_client_uses_hub_ca_cert(settings_fixture, monkeypatch, tmp_path):
    ca_cert = tmp_path / "caddy-root.crt"
    ca_cert.write_text("dummy", encoding="utf-8")
    settings_fixture.AEOS_HUB_CA_CERT = str(ca_cert)
    captured = {}

    class _FakeClient:
        is_closed = False

        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(hub_reporter.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(hub_reporter, "_client", None)
    hub_reporter._get_client()
    assert captured["verify"] == str(ca_cert)
