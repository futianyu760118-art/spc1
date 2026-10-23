"""智能体工具单测 — 工具 schema / 入参归一化与校验（不依赖真实 agent）"""

from app.services.assistant import agent_tools
from app.services.assistant.agent_tools import (
    build_agent_tools_schema,
    normalize_tool_input,
    validate_tool_input,
)


def _schema_names(include_order=True):
    return {s["function"]["name"] for s in build_agent_tools_schema(include_order=include_order)}


class TestBuildAgentToolsSchema:
    def test_all_tools_registered(self):
        assert _schema_names() == {
            "call_query_agent", "call_reasoning_agent", "call_order_agent", "hub_query"
        }

    def test_exclude_order_tool(self):
        assert _schema_names(include_order=False) == {
            "call_query_agent", "call_reasoning_agent", "hub_query"
        }

    def test_exclude_disabled(self):
        schemas = build_agent_tools_schema(exclude={"call_query_agent"})
        assert {s["function"]["name"] for s in schemas} == {
            "call_reasoning_agent", "call_order_agent", "hub_query"
        }

    def test_query_path_enum_matches_catalog(self):
        schema = next(s for s in build_agent_tools_schema() if s["function"]["name"] == "call_query_agent")
        enum = schema["function"]["parameters"]["properties"]["path"]["enum"]
        from app.services.assistant.task_router import QUERY_CATALOG

        assert len(enum) == len(QUERY_CATALOG) == 17
        assert enum == [c["path"] for c in QUERY_CATALOG]


class TestValidateToolInput:
    def test_query_valid(self):
        assert validate_tool_input(
            "call_query_agent", {"path": "/external/orders/list", "params": {}}
        ) is None

    def test_query_bad_path(self):
        assert validate_tool_input("call_query_agent", {"path": "/internal/x"}) is not None

    def test_reasoning_valid(self):
        assert validate_tool_input(
            "call_reasoning_agent",
            {"task_type": "order_delivery_analysis", "prompt": "分析交期", "businessObjectRef": "business://order/HJ-1"},
        ) is None

    def test_reasoning_normalizes_context(self):
        task_input = normalize_tool_input(
            "call_reasoning_agent",
            {"task_type": "order_delivery_analysis", "prompt": "x", "businessObjectRef": "business://order/HJ-1"},
        )
        assert task_input["context"] == {"businessObjectRef": "business://order/HJ-1"}
        assert task_input["constraints"] == {"read_only": True, "require_evidence": True}

    def test_reasoning_missing_ref(self):
        assert validate_tool_input(
            "call_reasoning_agent", {"task_type": "order_delivery_analysis", "prompt": "x"}
        ) is not None

    def test_order_valid(self):
        assert validate_tool_input(
            "call_order_agent", {"order_no": "HJ-1", "fields": {"shipping_plan": "2026-11-01"}}
        ) is None

    def test_order_field_not_allowed(self):
        assert validate_tool_input(
            "call_order_agent", {"order_no": "HJ-1", "fields": {"status": "closed"}}
        ) is not None

    def test_order_bad_date(self):
        assert validate_tool_input(
            "call_order_agent", {"order_no": "HJ-1", "fields": {"shipping_plan": "next week"}}
        ) is not None

    def test_order_empty_fields(self):
        assert validate_tool_input("call_order_agent", {"order_no": "HJ-1", "fields": {}}) is not None


class TestRegistryMetadata:
    def test_order_tool_requires_confirmation(self):
        from app.services.assistant.tool_registry import get_tool

        query = get_tool("call_query_agent")
        reasoning = get_tool("call_reasoning_agent")
        order = get_tool("call_order_agent")
        assert query.read_only is True and reasoning.read_only is True
        assert order.read_only is False
        assert order.requires_confirmation is True

    def test_hub_query_read_only(self):
        from app.services.assistant.tool_registry import get_tool

        hub = get_tool("hub_query")
        assert hub.read_only is True
        assert hub.requires_confirmation is False
        assert hub.category == "agent"

    def test_agent_tools_registered_at_import(self):
        import app.services.assistant.agent_tools as mod  # noqa: F401

        assert mod is agent_tools
