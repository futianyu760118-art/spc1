"""hub_client 单元测试：目录枚举兜底、错误映射、能力校验、网关 payload、轮询终态/超时。"""

import time

from app.services import hub_client


def _seed_catalog(templates):
    hub_client._catalog_cache["templates"] = templates
    hub_client._catalog_cache["fetched_at"] = time.monotonic()


def _reset_catalog():
    hub_client._catalog_cache["templates"] = None
    hub_client._catalog_cache["fetched_at"] = 0.0


async def test_capability_names_filters_self_and_fallback():
    _reset_catalog()
    assert hub_client.capability_names() == ["query_plm"]
    _seed_catalog([
        {"capability": "query_plm", "providerSystem": "hengjian-plm"},
        {"capability": "query_control_platform", "providerSystem": "control-platform"},
    ])
    assert hub_client.capability_names() == ["query_plm"]
    _reset_catalog()


async def test_provider_system_reads_catalog():
    _seed_catalog([{"capability": "query_plm", "providerSystem": "hengjian-plm"}])
    assert hub_client.provider_system("query_plm") == "hengjian-plm"
    assert hub_client.provider_system("query_erp") is None
    _reset_catalog()


def test_readable_error_maps_known_code():
    assert "借调单过多" in hub_client._readable_error("TOO_MANY_OPEN_ORDERS", "x")
    assert "不能通过 Hub 调用本系统能力" in hub_client._readable_error("SELF_BORROW_FORBIDDEN", "x")
    assert "Hub 返回错误" in hub_client._readable_error("UNKNOWN_CODE", "x")
    assert hub_client._readable_error(None, "fallback") == "fallback"


async def test_validate_capability_rejects_unknown_and_self():
    _seed_catalog([
        {"capability": "query_plm", "providerSystem": "hengjian-plm"},
        {"capability": "query_control_platform", "providerSystem": "control-platform"},
    ])
    assert await hub_client.validate_capability("query_plm") is None
    assert await hub_client.validate_capability("query_control_platform") == "不能通过 Hub 调用本系统能力"
    assert "不在" in await hub_client.validate_capability("query_erp")
    _reset_catalog()


async def test_invoke_capability_payload(monkeypatch):
    captured = {}

    async def _post(payload):
        captured.update(payload)
        return {"ok": True, "status": 202, "body": {"invocation": {"borrowOrderId": "borrow-1"}},
                "text": "", "error": None}

    monkeypatch.setattr(hub_client, "is_hub_enabled", lambda: True)
    monkeypatch.setattr(hub_client.gateway_client, "post_borrow_order", _post)
    out = await hub_client.invoke_capability(
        "query_plm", {"keyword": "HJ.1"}, to_system="hengjian-plm",
        caller={"systemId": "control-platform", "agentId": "AG-000001", "userId": "10086",
                "taskId": "AT-000123", "traceId": "trace-1"},
        trace_id="trace-1",
    )
    assert out["ok"] is True
    assert captured["toSystem"] == "hengjian-plm"
    assert captured["input"] == {"keyword": "HJ.1"}
    assert set(captured["caller"]) == {"systemId", "agentId", "userId", "taskId", "traceId"}
    assert "fromAgentId" not in captured
    assert captured["requestId"].startswith("spc-trace-1-")


async def test_invoke_capability_omits_caller_and_requires_provider(monkeypatch):
    captured = {}

    async def _post(payload):
        captured.update(payload)
        return {"ok": True, "status": 202, "body": {"invocation": {"borrowOrderId": "borrow-2"}},
                "text": "", "error": None}

    monkeypatch.setattr(hub_client, "is_hub_enabled", lambda: True)
    monkeypatch.setattr(hub_client.gateway_client, "post_borrow_order", _post)
    out = await hub_client.invoke_capability("query_plm", {"keyword": "HJ.1"}, to_system="hengjian-plm")
    assert out["ok"] is True
    assert "caller" not in captured

    missing = await hub_client.invoke_capability("query_plm", {"keyword": "HJ.1"})
    assert missing["ok"] is False
    assert "providerSystem" in missing["error"]


async def test_query_and_poll_completed(monkeypatch):
    async def _invoke(capability, params, **kwargs):
        return {"ok": True, "invocation": {"borrowOrderId": "borrow-1"}, "order": {},
                "request_id": "cp-test", "error": None}

    async def _poll(order_id):
        return {"ok": True, "order": {"status": "completed",
                                      "result": {"items": [{"projectNo": "HJ.1"}], "total": 1}}}

    monkeypatch.setattr(hub_client, "invoke_capability", _invoke)
    monkeypatch.setattr(hub_client, "get_borrow_order", _poll)
    out = await hub_client.query_and_poll("query_plm", {"keyword": "HJ.1"})
    assert out["ok"] is True
    assert out["borrow_order_id"] == "borrow-1"
    assert out["result"]["total"] == 1


async def test_query_and_poll_failed_status(monkeypatch):
    async def _invoke(capability, params, **kwargs):
        return {"ok": True, "invocation": {"borrowOrderId": "borrow-2"}, "order": {},
                "request_id": "cp-test", "error": None}

    async def _poll(order_id):
        return {"ok": True, "order": {"status": "failed"}}

    monkeypatch.setattr(hub_client, "invoke_capability", _invoke)
    monkeypatch.setattr(hub_client, "get_borrow_order", _poll)
    out = await hub_client.query_and_poll("query_plm", {})
    assert out["ok"] is False
    assert "已终止" in out["error"]


async def test_query_and_poll_timeout_reports_processing(monkeypatch):
    async def _invoke(capability, params, **kwargs):
        return {"ok": True, "invocation": {"borrowOrderId": "borrow-3"}, "order": {},
                "request_id": "cp-test", "error": None}

    async def _poll(order_id):
        return {"ok": True, "order": {"status": "running"}}

    monkeypatch.setattr(hub_client, "invoke_capability", _invoke)
    monkeypatch.setattr(hub_client, "get_borrow_order", _poll)
    out = await hub_client.query_and_poll("query_plm", {}, budget_s=0.01, interval_s=0.001)
    assert out["ok"] is False
    assert "处理中" in out["error"]
    assert out["borrow_order_id"] == "borrow-3"


async def test_query_and_poll_invoke_rejected(monkeypatch):
    async def _invoke(capability, params, **kwargs):
        return {"ok": False, "invocation": None, "order": None,
                "request_id": "cp-test", "error": "参数非法：xxx"}

    monkeypatch.setattr(hub_client, "invoke_capability", _invoke)
    out = await hub_client.query_and_poll("query_plm", {})
    assert out["ok"] is False
    assert "参数非法" in out["error"]
