"""智能体能力目录单元测试：单参工具过滤与目录结构。"""

from app.services.agent.capabilities import (
    ALL_CONFIGURABLE_CODES,
    CONFIGURABLE_CAPABILITIES,
    allowed_query_paths,
    allowed_reasoning_types,
    allowed_tool_names,
    allowed_write_fields,
    public_catalog,
)


def test_query_capability_enables_query_tool_only():
    tools = allowed_tool_names({"query.orders"})
    assert "call_query_agent" in tools
    assert "call_order_agent" not in tools
    assert "call_reasoning_agent" not in tools


def test_write_capabilities_split_by_field():
    cases = {
        "write.order_promised_date": "promised_date",
        "write.order_shipping_plan": "shipping_plan",
        "write.order_delivery_completed": "delivery_completed_date",
        "write.order_customer_inspection": "customer_inspection_date",
        "write.order_planned_start": "planned_start_date",
    }
    for code, field in cases.items():
        assert allowed_write_fields({code}) == {field}
        assert "call_order_agent" in allowed_tool_names({code})
    assert "write.order_schedule" not in CONFIGURABLE_CAPABILITIES


def test_empty_effective_yields_no_tools():
    assert allowed_tool_names(set()) == set()


def test_no_structural_capability_in_catalog():
    assert "team.manage" not in CONFIGURABLE_CAPABILITIES
    assert "team.manage" not in ALL_CONFIGURABLE_CODES


def test_public_catalog_shape():
    catalog = public_catalog()
    codes = {item["code"] for item in catalog}
    assert codes >= ALL_CONFIGURABLE_CODES
    for item in catalog:
        assert {"code", "name", "category", "read_only", "grantable", "tool_names",
                "structural", "scope_mode", "description"} <= set(item)
        assert item["grantable"] == (item["code"] in ALL_CONFIGURABLE_CODES)


def test_query_path_and_reasoning_type_filtering():
    paths = allowed_query_paths({"query.orders"})
    assert paths == {"/external/orders/list"}
    assert "/external/materials/list" in allowed_query_paths({"query.materials"})
    types = allowed_reasoning_types({"reason.orders"})
    assert "order_delivery_analysis" in types
    assert "quality_analysis" not in types


def test_capability_split_covers_all_query_paths():
    """拆分后的查询能力必须精确覆盖原捆绑能力的全部查询路径，且互不重叠。"""
    all_paths = [p for code in CONFIGURABLE_CAPABILITIES for p in CONFIGURABLE_CAPABILITIES[code].query_paths]
    assert len(all_paths) == len(set(all_paths)), "查询路径不得重复出现在多个能力中"
    assert "/external/order-details/list" in all_paths
    assert "/external/quality-trace/list" in all_paths
    assert "/external/inventory/availability" in all_paths
    assert "/external/material-supplies/list" in all_paths


def test_renamed_kitting_capability():
    assert "query.kitting" in CONFIGURABLE_CAPABILITIES
    assert "query.material_supplies" in CONFIGURABLE_CAPABILITIES
    assert "/external/material-kitting/results" in CONFIGURABLE_CAPABILITIES["query.kitting"].query_paths
