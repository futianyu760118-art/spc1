"""hub_reporter 单元测试：停用开关、payload 构造、网关转发、失败吞掉。"""

import asyncio

import pytest

from app.core.config import get_settings
from app.services.assistant import hub_reporter
from app.services.ai.base import TokenUsage


@pytest.fixture
def settings_fixture():
    settings = get_settings()
    saved = (settings.GATEWAY_BASE_URL, settings.GATEWAY_INTERNAL_TOKEN)
    yield settings
    settings.GATEWAY_BASE_URL, settings.GATEWAY_INTERNAL_TOKEN = saved


def _enable(settings, gateway_base="http://gateway-mock"):
    settings.GATEWAY_BASE_URL = gateway_base
    settings.GATEWAY_INTERNAL_TOKEN = "test-gateway-token"


def _disable(settings):
    settings.GATEWAY_BASE_URL = ""
    settings.GATEWAY_INTERNAL_TOKEN = ""


async def test_disabled_skips_report(settings_fixture, monkeypatch):
    _disable(settings_fixture)
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
    assert payload["durationMs"] == 12
    assert "endedAt" not in payload
    assert "usage" not in payload


async def test_top_level_task_fields(settings_fixture, monkeypatch):
    """阻塞 3 对齐：taskId / stepId / tool / confirmationId 放事件顶层，缺省不出现。"""
    _enable(settings_fixture)
    captured = []

    async def _stub(payload):
        captured.append(payload)

    monkeypatch.setattr(hub_reporter, "_post", _stub)
    hub_reporter.report_assistant_event(
        "s1", "step_completed", "查询智能体", status="completed", summary="查询 销售订单列表",
        task_id="task-abc", step_id=2, tool="call_query_agent", confirmation_id="wc-xyz",
    )
    hub_reporter.report_assistant_event("s1", "message", "用户消息", summary="hi")
    await asyncio.sleep(0.01)
    assert len(captured) == 2
    step = captured[0]
    assert step["taskId"] == "task-abc"
    assert step["stepId"] == 2
    assert step["tool"] == "call_query_agent"
    assert step["confirmationId"] == "wc-xyz"
    msg = captured[1]
    assert "taskId" not in msg
    assert "stepId" not in msg
    assert "tool" not in msg
    assert "confirmationId" not in msg


async def test_post_degrades_when_hub_rejects_optional_fields(settings_fixture, monkeypatch):
    """Hub 版本不支持顶层 taskId/stepId/tool 时，剥离后重发并缓存，后续事件直接降级。"""
    _enable(settings_fixture)
    monkeypatch.setattr(hub_reporter, "_rejected_event_fields", set())
    payloads = []

    async def _post(payload):
        payloads.append(payload)
        if len(payloads) == 1:
            return {"ok": False, "status": 400,
                    "body": {"error": "不支持的字段：taskId, stepId, tool", "code": "INVALID_ARGUMENT"},
                    "text": '{"error":"不支持的字段：taskId, stepId, tool","code":"INVALID_ARGUMENT"}',
                    "error": "网关返回 HTTP 400"}
        return {"ok": True, "status": 201, "body": {}, "text": "{}", "error": None}

    monkeypatch.setattr(hub_reporter.gateway_client, "post_assistant_event", _post)
    payload = {
        "eventId": "e1", "traceId": "s1", "event": "tool_call",
        "taskId": "task-1", "stepId": 1, "tool": "call_query_agent", "confirmationId": "wc-1",
    }

    await hub_reporter._post(dict(payload))
    assert len(payloads) == 2
    assert "taskId" not in payloads[1]
    assert "stepId" not in payloads[1]
    assert "tool" not in payloads[1]
    assert payloads[1]["confirmationId"] == "wc-1"

    await hub_reporter._post(dict(payload))
    assert len(payloads) == 3
    assert "taskId" not in payloads[2]
    assert payloads[2]["confirmationId"] == "wc-1"


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


async def test_post_forwards_payload_to_gateway(settings_fixture, monkeypatch):
    _enable(settings_fixture)
    captured = []

    async def _post(payload):
        captured.append(payload)
        return {"ok": True, "status": 200, "body": {"accepted": True}, "text": "", "error": None}

    monkeypatch.setattr(hub_reporter.gateway_client, "post_assistant_event", _post)
    payload = {"traceId": "s1", "event": "message", "eventId": "e1"}
    await hub_reporter._post(dict(payload))
    assert captured == [payload]


async def test_post_swallows_gateway_error(settings_fixture, monkeypatch):
    _enable(settings_fixture)
    captured = []

    async def _post(payload):
        captured.append(payload)
        return {"ok": False, "status": 0, "body": None, "text": "", "error": "网关连接失败"}

    monkeypatch.setattr(hub_reporter.gateway_client, "post_assistant_event", _post)
    await hub_reporter._post({"traceId": "s1", "event": "message", "eventId": "e1"})
    assert len(captured) == 1
