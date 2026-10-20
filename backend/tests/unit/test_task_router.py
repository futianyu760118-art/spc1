"""任务路由单测 — 入参校验与路由决策分支（不依赖 DB / 真实 LLM）"""

import json

from app.services.assistant import task_router
from app.services.assistant.task_router import (
    RoutingClassification,
    _trim_result_for_render,
    validate_task_input,
)


class TestValidateTaskInput:
    def test_query_valid(self):
        assert (
            validate_task_input(
                "query_control_platform",
                {"path": "/external/orders/list", "params": {"keyword": "HJ"}},
            )
            is None
        )

    def test_query_path_not_in_whitelist(self):
        reason = validate_task_input("query_control_platform", {"path": "/internal/secret"})
        assert reason and "白名单" in reason

    def test_query_params_must_be_object(self):
        reason = validate_task_input(
            "query_control_platform", {"path": "/external/orders/list", "params": "x"}
        )
        assert reason is not None

    def test_reasoning_valid(self):
        assert (
            validate_task_input(
                "reason_control_platform",
                {
                    "prompt": "分析交期",
                    "task_type": "order_delivery_analysis",
                    "context": {"businessObjectRef": "business://order/HJ-1"},
                },
            )
            is None
        )

    def test_reasoning_bad_task_type(self):
        reason = validate_task_input(
            "reason_control_platform",
            {"prompt": "x", "task_type": "nope", "context": {"businessObjectRef": "business://order/HJ-1"}},
        )
        assert reason is not None

    def test_reasoning_missing_business_ref(self):
        reason = validate_task_input(
            "reason_control_platform",
            {"prompt": "x", "task_type": "order_delivery_analysis", "context": {}},
        )
        assert reason is not None

    def test_order_valid(self):
        assert (
            validate_task_input(
                "update_control_platform_order",
                {"order_no": "HJ-1", "fields": {"shipping_plan": "2026-11-01"}},
            )
            is None
        )

    def test_order_field_not_allowed(self):
        reason = validate_task_input(
            "update_control_platform_order",
            {"order_no": "HJ-1", "fields": {"status": "closed"}},
        )
        assert reason is not None

    def test_order_bad_date(self):
        reason = validate_task_input(
            "update_control_platform_order",
            {"order_no": "HJ-1", "fields": {"shipping_plan": "tomorrow"}},
        )
        assert reason is not None

    def test_unknown_capability(self):
        assert validate_task_input("fly_to_moon", {}) is not None


class TestTrimResultForRender:
    def test_items_within_limit_untouched(self):
        result = {"total": 2, "items": [{"order_no": "A"}, {"order_no": "B"}]}
        assert _trim_result_for_render(result) == result

    def test_too_many_items_truncated(self):
        result = {"total": 30, "items": [{"order_no": f"O{i}"} for i in range(30)]}
        trimmed = _trim_result_for_render(result, max_items=20)
        assert len(trimmed["items"]) == 20
        assert trimmed["_items_truncated"] is True
        assert trimmed["_items_shown"] == 20
        assert trimmed["total"] == 30

    def test_oversized_items_shrink_but_json_stays_valid(self):
        big_item = {"order_no": "X" * 500, "customer": "Y" * 500}
        result = {"total": 50, "items": [dict(big_item) for _ in range(50)]}
        trimmed = _trim_result_for_render(result, max_items=50, max_chars=3000)
        assert len(json.dumps(trimmed, ensure_ascii=False)) <= 3000
        assert trimmed["_items_truncated"] is True
        assert trimmed["items"]

    def test_non_items_result_untouched(self):
        result = {"task_id": "t1", "summary": "ok"}
        assert _trim_result_for_render(result) == result


class TestRouteTask:
    async def test_local_query_dispatched(self, monkeypatch):
        calls = {}

        async def fake_classify(message, history, model_override=None):
            return RoutingClassification(
                decision="local",
                capability="query_control_platform",
                input={"path": "/external/orders/list", "params": {}},
                reason="查询",
            )

        async def fake_dispatch(agent_key, task_input):
            calls["key"] = agent_key
            calls["input"] = task_input
            return {"online": True, "ok": True, "result": {"items": [], "total": 0}}

        monkeypatch.setattr(task_router, "classify_task", fake_classify)
        monkeypatch.setattr(task_router, "dispatch_local", fake_dispatch)
        outcome = await task_router.route_task("查一下订单", [])
        assert outcome["decision"] == "local"
        assert outcome["executed"] is True
        assert outcome["agent_key"] == "query"
        assert calls["key"] == "query"
        assert calls["input"] == {"path": "/external/orders/list", "params": {}}

    async def test_local_agent_offline_downgrades_to_hub(self, monkeypatch):
        async def fake_classify(message, history, model_override=None):
            return RoutingClassification(
                decision="local",
                capability="query_control_platform",
                input={"path": "/external/orders/list", "params": {}},
                reason="查询",
            )

        async def fake_dispatch(agent_key, task_input):
            return {"online": False, "reason": "EXECUTION_QUERY_AGENT_BASE_URL 未配置"}

        monkeypatch.setattr(task_router, "classify_task", fake_classify)
        monkeypatch.setattr(task_router, "dispatch_local", fake_dispatch)
        outcome = await task_router.route_task("查一下订单", [])
        assert outcome["decision"] == "hub"
        assert outcome["executed"] is False
        assert outcome["dispatch_error"]

    async def test_invalid_input_downgrades_to_hub_without_dispatch(self, monkeypatch):
        async def fake_classify(message, history, model_override=None):
            return RoutingClassification(
                decision="local",
                capability="query_control_platform",
                input={"path": "/internal/secret", "params": {}},
                reason="查询",
            )

        dispatched = {"v": False}

        async def fake_dispatch(agent_key, task_input):
            dispatched["v"] = True
            return {"online": True, "ok": True, "result": {}}

        monkeypatch.setattr(task_router, "classify_task", fake_classify)
        monkeypatch.setattr(task_router, "dispatch_local", fake_dispatch)
        outcome = await task_router.route_task("查一下", [])
        assert outcome["decision"] == "hub"
        assert dispatched["v"] is False

    async def test_hub_decision_passthrough(self, monkeypatch):
        async def fake_classify(message, history, model_override=None):
            return RoutingClassification(decision="hub", reason="本地无法完成")

        monkeypatch.setattr(task_router, "classify_task", fake_classify)
        outcome = await task_router.route_task("帮我写周报", [])
        assert outcome["decision"] == "hub"
        assert outcome["executed"] is False

    async def test_none_decision(self, monkeypatch):
        async def fake_classify(message, history, model_override=None):
            return RoutingClassification(decision="none", reason="闲聊")

        monkeypatch.setattr(task_router, "classify_task", fake_classify)
        outcome = await task_router.route_task("你好", [])
        assert outcome["decision"] == "none"
        assert outcome["executed"] is False

    async def test_classify_failure_failsafe_none(self, monkeypatch):
        async def fake_structured_output(prompt, schema, options=None, provider_name=None):
            raise RuntimeError("llm down")

        monkeypatch.setattr(task_router.ai_service, "structured_output", fake_structured_output)
        classification = await task_router.classify_task("查订单", [])
        assert classification.decision == "none"
        outcome = await task_router.route_task("查订单", [])
        assert outcome["decision"] == "none"
        assert outcome["executed"] is False
