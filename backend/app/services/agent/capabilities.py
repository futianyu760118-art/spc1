"""智能体能力目录（代码内静态声明）：查询/推理/写三类 + 占位。

effective 能力由用户团队成员能力并集决定（见 context.load_user_context）；
required_permissions 仅作目录元数据保留，不再参与门控。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass(frozen=True)
class Capability:
    code: str
    name: str
    category: str
    read_only: bool
    required_permissions: Dict[str, str] = field(default_factory=dict)
    scope_mode: str = "org"
    tool_names: tuple = ()
    endpoint_codes: tuple = ()
    query_paths: tuple = ()
    reasoning_types: tuple = ()
    write_fields: tuple = ()
    structural: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "category": self.category,
            "read_only": self.read_only,
            "scope_mode": self.scope_mode,
            "tool_names": list(self.tool_names),
            "write_fields": list(self.write_fields),
            "structural": self.structural,
            "description": self.description,
        }


CAPABILITIES: Dict[str, Capability] = {
    "query.orders": Capability(
        code="query.orders", name="订单查询", category="query", read_only=True,
        required_permissions={"orders.list": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("orders.list",),
        query_paths=("/external/orders/list",),
        description="销售订单只读查询（按订单负责人/部门过滤）",
    ),
    "query.order_details": Capability(
        code="query.order_details", name="订单明细查询", category="query", read_only=True,
        required_permissions={"orders.list": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("order_details.list",),
        query_paths=("/external/order-details/list",),
        description="销售订单明细只读查询",
    ),
    "query.kitting": Capability(
        code="query.kitting", name="齐套查询", category="query", read_only=True,
        required_permissions={"materials.kit_analysis": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("kitting.results", "kitting.shortages", "kitting.demands"),
        query_paths=(
            "/external/material-kitting/results",
            "/external/material-kitting/shortages",
            "/external/material-kitting/demands",
        ),
        description="齐套结果、缺料清单与齐套需求只读查询（经订单号关联过滤）",
    ),
    "query.material_supplies": Capability(
        code="query.material_supplies", name="物料供给查询", category="query", read_only=True,
        required_permissions={"materials.kit_analysis": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("material.supplies",),
        query_paths=("/external/material-supplies/list",),
        description="物料供给只读查询",
    ),
    "query.quality": Capability(
        code="query.quality", name="品质异常查询", category="query", read_only=True,
        required_permissions={"exceptions.quality": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("quality_issues.list",),
        query_paths=("/external/quality-issues/list",),
        description="品质异常只读查询（订单/负责人/部门过滤）",
    ),
    "query.quality_trace": Capability(
        code="query.quality_trace", name="质量追溯查询", category="query", read_only=True,
        required_permissions={"exceptions.quality": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("quality_trace.list",),
        query_paths=("/external/quality-trace/list",),
        description="质量追溯只读查询",
    ),
    "query.materials": Capability(
        code="query.materials", name="物料查询", category="query", read_only=True,
        required_permissions={"topbar.ai_search": "read"},
        scope_mode="global",
        tool_names=("call_query_agent",),
        endpoint_codes=("materials.list",),
        query_paths=("/external/materials/list",),
        description="物料主数据只读查询",
    ),
    "query.suppliers": Capability(
        code="query.suppliers", name="供应商查询", category="query", read_only=True,
        required_permissions={"topbar.ai_search": "read"},
        scope_mode="global",
        tool_names=("call_query_agent",),
        endpoint_codes=("suppliers.list",),
        query_paths=("/external/suppliers/list",),
        description="供应商主数据只读查询",
    ),
    "query.boms": Capability(
        code="query.boms", name="BOM 查询", category="query", read_only=True,
        required_permissions={"topbar.ai_search": "read"},
        scope_mode="global",
        tool_names=("call_query_agent",),
        endpoint_codes=("boms.tree",),
        query_paths=("/external/boms/tree",),
        description="BOM 结构只读查询",
    ),
    "query.inventory": Capability(
        code="query.inventory", name="库存查询", category="query", read_only=True,
        required_permissions={"topbar.ai_search": "read"},
        scope_mode="global",
        tool_names=("call_query_agent",),
        endpoint_codes=("inventory.availability",),
        query_paths=("/external/inventory/availability",),
        description="库存可用量只读查询",
    ),
    "reason.orders": Capability(
        code="reason.orders", name="订单交期推理", category="reason", read_only=True,
        required_permissions={"orders.list": "read"},
        tool_names=("call_reasoning_agent",),
        endpoint_codes=("reasoning.analyze",),
        reasoning_types=("order_delivery_analysis",),
        description="订单交期/交付风险只读推理分析",
    ),
    "reason.materials": Capability(
        code="reason.materials", name="齐套缺料推理", category="reason", read_only=True,
        required_permissions={"materials.kit_analysis": "read"},
        tool_names=("call_reasoning_agent",),
        endpoint_codes=("reasoning.analyze",),
        reasoning_types=("material_kitting_analysis",),
        description="齐套/缺料风险只读推理分析",
    ),
    "reason.quality": Capability(
        code="reason.quality", name="品质推理", category="reason", read_only=True,
        required_permissions={"exceptions.quality": "read"},
        tool_names=("call_reasoning_agent",),
        endpoint_codes=("reasoning.analyze",),
        reasoning_types=("quality_analysis",),
        description="品质异常只读推理分析",
    ),
    "write.order_promised_date": Capability(
        code="write.order_promised_date", name="修改合同交期", category="write", read_only=False,
        required_permissions={"orders.list": "update"},
        tool_names=("call_order_agent",),
        endpoint_codes=("orders.write",),
        write_fields=("promised_date",),
        description="修改订单合同交期（必须人工确认）",
    ),
    "write.order_shipping_plan": Capability(
        code="write.order_shipping_plan", name="修改出货计划", category="write", read_only=False,
        required_permissions={"orders.list": "update"},
        tool_names=("call_order_agent",),
        endpoint_codes=("orders.write",),
        write_fields=("shipping_plan",),
        description="修改订单出货计划日期（必须人工确认）",
    ),
    "write.order_delivery_completed": Capability(
        code="write.order_delivery_completed", name="修改发货完成时间", category="write", read_only=False,
        required_permissions={"orders.list": "update"},
        tool_names=("call_order_agent",),
        endpoint_codes=("orders.write",),
        write_fields=("delivery_completed_date",),
        description="修改订单发货完成时间（必须人工确认）",
    ),
    "write.order_customer_inspection": Capability(
        code="write.order_customer_inspection", name="修改客户验货时间", category="write", read_only=False,
        required_permissions={"orders.list": "update"},
        tool_names=("call_order_agent",),
        endpoint_codes=("orders.write",),
        write_fields=("customer_inspection_date",),
        description="修改订单客户验货时间（必须人工确认）",
    ),
    "write.order_planned_start": Capability(
        code="write.order_planned_start", name="修改上线时间", category="write", read_only=False,
        required_permissions={"orders.list": "update"},
        tool_names=("call_order_agent",),
        endpoint_codes=("orders.write",),
        write_fields=("planned_start_date",),
        description="修改订单上线时间（必须人工确认）",
    ),
    "write.feedback_create": Capability(
        code="write.feedback_create", name="创建问题反馈", category="write", read_only=False,
        required_permissions={"topbar.feedback": "read"},
        tool_names=("create_feedback", "revoke_feedback"),
        description="代用户提交问题反馈，并可撤销本人待处理的反馈",
    ),
    "team.manage": Capability(
        code="team.manage", name="团队管理", category="team", read_only=False,
        structural=True,
        tool_names=("list_my_subordinates",),
        description="查看直属子智能体并委派只读任务（有直属子智能体即具备）",
    ),
    "query.production": Capability(
        code="query.production", name="生产域查询（首期未开放）", category="query", read_only=True,
        scope_mode="unsupported", description="生产域范围规则验证后再开放",
    ),
    "hub.query": Capability(
        code="hub.query", name="Hub 跨系统查询（首期未开放）", category="query", read_only=True,
        scope_mode="unsupported", description="避免绕过 SPC 数据范围",
    ),
}

CONFIGURABLE_CAPABILITIES: Dict[str, Capability] = {
    code: cap for code, cap in CAPABILITIES.items()
    if not cap.structural and cap.scope_mode != "unsupported"
}

ALL_CONFIGURABLE_CODES: Set[str] = set(CONFIGURABLE_CAPABILITIES)


def allowed_tool_names(effective: Set[str]) -> Set[str]:
    names: Set[str] = set()
    for code in effective:
        cap = CONFIGURABLE_CAPABILITIES.get(code)
        if cap:
            names |= set(cap.tool_names)
    return names


def allowed_query_paths(effective: Set[str]) -> Set[str]:
    paths: Set[str] = set()
    for code in effective:
        cap = CONFIGURABLE_CAPABILITIES.get(code)
        if cap:
            paths |= set(cap.query_paths)
    return paths


def allowed_reasoning_types(effective: Set[str]) -> Set[str]:
    types: Set[str] = set()
    for code in effective:
        cap = CONFIGURABLE_CAPABILITIES.get(code)
        if cap:
            types |= set(cap.reasoning_types)
    return types


def allowed_write_fields(effective: Set[str]) -> Set[str]:
    """团队写能力并集对应的订单可写字段集合（call_order_agent 的字段门控）。"""
    fields: Set[str] = set()
    for code in effective:
        cap = CONFIGURABLE_CAPABILITIES.get(code)
        if cap:
            fields |= set(cap.write_fields)
    return fields


def capabilities_for_endpoint(endpoint_code: str) -> Set[str]:
    return {
        code for code, cap in CONFIGURABLE_CAPABILITIES.items()
        if endpoint_code in cap.endpoint_codes
    }


def public_catalog() -> List[dict]:
    items = [
        {**cap.to_dict(), "grantable": code in CONFIGURABLE_CAPABILITIES}
        for code, cap in CAPABILITIES.items()
    ]
    return sorted(items, key=lambda item: (item["category"], item["code"]))
