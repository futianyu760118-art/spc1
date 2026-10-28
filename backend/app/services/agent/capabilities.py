"""智能体能力目录与可授予性判断。

能力目录是代码内静态声明：查询/推理/写/任务四类。主管配置只能授予
自己当前有效能力的子集；角色已有的能力始终是基线，禁用只能收紧不能扩权。
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set


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
            "structural": self.structural,
            "description": self.description,
        }


CAPABILITIES: Dict[str, Capability] = {
    "query.orders": Capability(
        code="query.orders", name="订单查询", category="query", read_only=True,
        required_permissions={"orders.list": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("orders.list", "order_details.list"),
        query_paths=("/external/orders/list", "/external/order-details/list"),
        description="销售订单与订单明细只读查询（按订单负责人/部门过滤）",
    ),
    "query.materials": Capability(
        code="query.materials", name="物料齐套查询", category="query", read_only=True,
        required_permissions={"materials.kit_analysis": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("kitting.results", "kitting.shortages", "kitting.demands", "material.supplies"),
        query_paths=(
            "/external/material-kitting/results",
            "/external/material-kitting/shortages",
            "/external/material-kitting/demands",
            "/external/material-supplies/list",
        ),
        description="齐套、缺料、物料供给只读查询（经订单号关联过滤）",
    ),
    "query.quality": Capability(
        code="query.quality", name="品质异常查询", category="query", read_only=True,
        required_permissions={"exceptions.quality": "read"},
        tool_names=("call_query_agent",),
        endpoint_codes=("quality_issues.list", "quality_trace.list"),
        query_paths=("/external/quality-issues/list", "/external/quality-trace/list"),
        description="品质异常与质量追溯只读查询（订单/负责人/部门过滤）",
    ),
    "query.masterdata": Capability(
        code="query.masterdata", name="主数据查询", category="query", read_only=True,
        required_permissions={"topbar.ai_search": "read"},
        scope_mode="global",
        tool_names=("call_query_agent",),
        endpoint_codes=("materials.list", "suppliers.list", "boms.tree", "inventory.availability"),
        query_paths=(
            "/external/materials/list",
            "/external/suppliers/list",
            "/external/boms/tree",
            "/external/inventory/availability",
        ),
        description="物料/供应商/BOM/库存等全局共享主数据只读查询",
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
    "write.order_schedule": Capability(
        code="write.order_schedule", name="订单计划写入", category="write", read_only=False,
        required_permissions={"orders.list": "update"},
        tool_names=("call_order_agent",),
        endpoint_codes=("orders.schedule.update",),
        description="修改订单出货计划/发货完成/客户验货/上线时间（必须人工确认）",
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


def _has_required(permissions: Dict[str, List[str]], required: Dict[str, str]) -> bool:
    """按 PermissionChecker 语义检查 resource.action（含父级 fallback）。"""
    for resource, action in required.items():
        candidates = [resource]
        parts = resource.split(".")
        candidates.extend(".".join(parts[:i]) for i in range(len(parts) - 1, 0, -1))
        if not any(action in (permissions.get(c) or []) for c in candidates):
            return False
    return True


def baseline_capabilities(permissions: Dict[str, List[str]]) -> Set[str]:
    """角色权限满足的能力基线（不含主管授予）。"""
    return {
        code for code, cap in CONFIGURABLE_CAPABILITIES.items()
        if _has_required(permissions or {}, cap.required_permissions)
    }


def resolve_capabilities(
    permissions: Dict[str, List[str]],
    policy: Optional[dict],
    grant_ceiling: Optional[Set[str]],
) -> Set[str]:
    """effective = (baseline ∪ (granted ∩ ceiling)) − disabled。"""
    baseline = baseline_capabilities(permissions)
    policy = policy or {}
    granted = set(policy.get("granted") or []) & ALL_CONFIGURABLE_CODES
    if grant_ceiling is not None:
        granted &= grant_ceiling
    disabled = set(policy.get("disabled") or []) & ALL_CONFIGURABLE_CODES
    return (baseline | granted) - disabled


def structural_tools(is_supervisor: bool, can_manage_team: bool) -> Set[str]:
    """结构性工具：内部用户可查看直属成员；有直属成员后可委派。"""
    names: Set[str] = set()
    if can_manage_team:
        names.add("list_my_subordinates")
    if is_supervisor:
        names.add("delegate_task")
    return names


def allowed_tool_names(effective: Set[str], is_supervisor: bool, can_manage_team: bool) -> Set[str]:
    names: Set[str] = set()
    for code in effective:
        cap = CONFIGURABLE_CAPABILITIES.get(code)
        if cap:
            names |= set(cap.tool_names)
    names |= structural_tools(is_supervisor, can_manage_team)
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
