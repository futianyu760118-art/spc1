"""公共审批引擎纯函数单元测试（不依赖数据库）。"""

from app.services.common.approval_engine import _cond_match, check_node_permission

NODE_NO_CONDITION = {"seq": 1, "label": "节点1", "role": "purchase_manager"}
NODE_DYNAMIC = {"seq": 1, "label": "动态节点", "approvers": [{"username": "张三", "user_id": 7}]}


class TestCheckNodePermission:
    def test_admin_bypasses_all(self):
        ok, msg = check_node_permission({"seq": 1, "role": "finance"}, "任何人", "admin")
        assert ok is True and msg == ""

    def test_dynamic_approver_match_username(self):
        ok, _ = check_node_permission(NODE_DYNAMIC, "张三", "quality")
        assert ok is True

    def test_dynamic_approver_match_user_id(self):
        ok, _ = check_node_permission(NODE_DYNAMIC, "7", "quality")
        assert ok is True

    def test_dynamic_approver_mismatch(self):
        ok, msg = check_node_permission(NODE_DYNAMIC, "李四", "quality")
        assert ok is False and "张三" in msg

    def test_dynamic_approvers_empty_is_resolver_failure(self):
        ok, msg = check_node_permission({"seq": 1, "approvers": []}, "张三", "quality")
        assert ok is False and "解析失败" in msg

    def test_fixed_role_match(self):
        ok, _ = check_node_permission(NODE_NO_CONDITION, "采购经理甲", "purchase_manager")
        assert ok is True

    def test_fixed_role_mismatch(self):
        ok, msg = check_node_permission(NODE_NO_CONDITION, "采购经理甲", "finance")
        assert ok is False and "purchase_manager" in msg

    def test_node_without_role_or_approvers_allows(self):
        ok, _ = check_node_permission({"seq": 1, "label": "空节点"}, "乙", "unknown_role")
        assert ok is True


class TestCondMatch:
    def test_no_condition_matches(self):
        assert _cond_match(None, {}) is True
        assert _cond_match({}, {"claim_amount": 1}) is True

    def test_condition_without_field_matches(self):
        assert _cond_match({"op": ">=", "value": 1000}, {}) is True

    def test_in_operator(self):
        cond = {"field": "claim_reason", "op": "in", "value": ["a", "b"]}
        assert _cond_match(cond, {"claim_reason": "a"}) is True
        assert _cond_match(cond, {"claim_reason": "c"}) is False

    def test_gte_boundary(self):
        cond = {"field": "claim_amount", "op": ">=", "value": 1000}
        assert _cond_match(cond, {"claim_amount": 1000}) is True
        assert _cond_match(cond, {"claim_amount": 999.99}) is False

    def test_all_comparison_operators(self):
        assert _cond_match({"field": "v", "op": ">", "value": 1}, {"v": 2}) is True
        assert _cond_match({"field": "v", "op": "<", "value": 1}, {"v": 2}) is False
        assert _cond_match({"field": "v", "op": "<=", "value": 2}, {"v": 2}) is True
        assert _cond_match({"field": "v", "op": "==", "value": 2}, {"v": 2}) is True
        assert _cond_match({"field": "v", "op": "!=", "value": 2}, {"v": 2}) is False

    def test_non_numeric_value_fails_closed(self):
        assert _cond_match({"field": "v", "op": ">=", "value": 1}, {"v": "abc"}) is False
        assert _cond_match({"field": "v", "op": ">=", "value": 1}, {"v": None}) is False

    def test_missing_field_value_fails_closed(self):
        assert _cond_match({"field": "v", "op": ">=", "value": 1}, {}) is False
