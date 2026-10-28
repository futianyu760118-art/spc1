"""智能体能力策略单元测试：基线、授予上限、禁用、工具过滤。"""

from app.services.agent.capabilities import (
    ALL_CONFIGURABLE_CODES,
    allowed_query_paths,
    allowed_reasoning_types,
    allowed_tool_names,
    baseline_capabilities,
    resolve_capabilities,
)


def test_baseline_by_role_permissions():
    perms = {"orders.list": ["read"], "materials.kit_analysis": ["read"]}
    baseline = baseline_capabilities(perms)
    assert "query.orders" in baseline
    assert "query.materials" in baseline
    assert "reason.orders" in baseline
    assert "write.order_schedule" not in baseline


def test_granted_cannot_exceed_parent_ceiling():
    perms = {"dashboard": ["read"]}
    parent_effective = {"query.orders"}
    effective = resolve_capabilities(
        perms,
        {"granted": ["query.orders", "write.order_schedule"], "disabled": []},
        parent_effective,
    )
    assert "query.orders" in effective
    assert "write.order_schedule" not in effective


def test_disabled_can_tighten_role_baseline():
    perms = {"orders.list": ["read"]}
    effective = resolve_capabilities(
        perms, {"granted": [], "disabled": ["query.orders"]}, ALL_CONFIGURABLE_CODES,
    )
    assert "query.orders" not in effective


def test_tool_and_path_filtering():
    effective = {"query.orders", "reason.orders"}
    tools = allowed_tool_names(effective, is_supervisor=False, can_manage_team=True)
    assert "call_query_agent" in tools
    assert "call_order_agent" not in tools
    assert "list_my_subordinates" in tools
    assert "delegate_task" not in tools
    paths = allowed_query_paths(effective)
    assert "/external/orders/list" in paths
    assert "/external/materials/list" not in paths
    types = allowed_reasoning_types(effective)
    assert "order_delivery_analysis" in types
    assert "quality_analysis" not in types


def test_supervisor_structural_tools():
    tools = allowed_tool_names(set(), is_supervisor=True, can_manage_team=True)
    assert "delegate_task" in tools
    assert "list_my_subordinates" in tools
