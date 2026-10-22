"""hub_client 单元测试：目录枚举兜底、错误映射、能力校验、轮询终态/超时（全程 monkeypatch，不打真实 Hub）。"""

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


def test_readable_error_maps_known_code():
    assert "借调单过多" in hub_client._readable_error("TOO_MANY_OPEN_ORDERS", "x")
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
