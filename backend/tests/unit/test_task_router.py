"""任务能力目录单测 — 入参校验与结果裁剪（不依赖 DB / 真实 LLM）"""

import json

from app.services.assistant.task_router import (
    trim_result,
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


class TestTrimResult:
    def test_items_within_limit_untouched(self):
        result = {"total": 2, "items": [{"order_no": "A"}, {"order_no": "B"}]}
        assert trim_result(result) == result

    def test_too_many_items_truncated(self):
        result = {"total": 30, "items": [{"order_no": f"O{i}"} for i in range(30)]}
        trimmed = trim_result(result, max_items=20)
        assert len(trimmed["items"]) == 20
        assert trimmed["_items_truncated"] is True
        assert trimmed["_items_shown"] == 20
        assert trimmed["total"] == 30

    def test_oversized_items_shrink_but_json_stays_valid(self):
        big_item = {"order_no": "X" * 500, "customer": "Y" * 500}
        result = {"total": 50, "items": [dict(big_item) for _ in range(50)]}
        trimmed = trim_result(result, max_items=50, max_chars=3000)
        assert len(json.dumps(trimmed, ensure_ascii=False)) <= 3000
        assert trimmed["_items_truncated"] is True
        assert trimmed["items"]

    def test_non_items_result_untouched(self):
        result = {"task_id": "t1", "summary": "ok"}
        assert trim_result(result) == result
