from copy import deepcopy
from typing import Dict, List


FULL_ACTIONS = ["create", "read", "update", "delete"]


ROLE_PERMISSION_ADDITIONS: Dict[str, Dict[str, List[str]]] = {
    "admin": {
        "production.schedule_plans": FULL_ACTIONS,
        "production.daily_report": FULL_ACTIONS,
        "production.labor_price_audit": ["read"],
        "production.order_wage_lookup": ["read"],
        "production.monthly_capacity_plan": ["read", "manage"],
        "exceptions.product_samples": FULL_ACTIONS,
        "rules.order_standards": FULL_ACTIONS,
        "rules.work_instructions": FULL_ACTIONS,
        "finance.data": ["read"],
        "materials.scrap_inventory": ["read"],
        "materials.task_stock_check": ["read"],
        "materials.inventory_board": ["read"],
        "materials.occupancy": ["read"],
        "quality.supplier_claim": FULL_ACTIONS,
        "quality.supplier_claim.archive_delete": ["delete"],
        "approval.pending": ["read"],
        "approval.initiate": ["read"],
        "approval.config": ["read", "update"],
        "approval.business": ["read", "update"],
        "materials.mrp": ["read", "run", "review", "convert", "param"],
        "materials.purchase_requisition": ["read", "create", "update", "convert"],
        "backup": ["read", "manage"],
    },
    "planner": {
        "production.schedule_plans": ["read", "update"],
        "production.order_wage_lookup": ["read"],
        "production.monthly_capacity_plan": ["read", "manage"],
        "exceptions.product_samples": ["read", "update"],
        "materials.scrap_inventory": ["read"],
        "materials.task_stock_check": ["read"],
        "materials.inventory_board": ["read"],
        "materials.occupancy": ["read"],
        "materials.mrp": ["read", "run", "review", "param"],
        "materials.purchase_requisition": ["read", "create", "update", "convert"],
        "approval.initiate": ["read"],
    },
    "purchaser": {
        "materials.scrap_inventory": ["read"],
        "materials.task_stock_check": ["read"],
        "materials.inventory_board": ["read"],
        "materials.occupancy": ["read"],
        "materials.mrp": ["read", "review", "convert"],
        "materials.purchase_requisition": ["read", "update", "convert"],
    },
    "manager": {
        "production.schedule_plans": ["read", "update"],
        "production.order_wage_lookup": ["read"],
        "production.monthly_capacity_plan": ["read", "manage"],
        "exceptions.product_samples": ["read", "update"],
        "rules.order_standards": ["read", "update"],
        "rules.work_instructions": ["read", "update"],
        "users": ["read", "update"],
        "users.reset_password": ["reset_password"],
        "roles": ["read", "update"],
        "materials.subcontract_orders": ["read"],
        "finance.data": ["read"],
        "materials.scrap_inventory": ["read"],
        "materials.task_stock_check": ["read"],
        "materials.inventory_board": ["read"],
        "materials.occupancy": ["read"],
        "quality.supplier_claim": ["read"],
        "approval.pending": ["read"],
        "approval.initiate": ["read"],
        "materials.mrp": ["read"],
        "materials.purchase_requisition": ["read"],
    },
    "warehouse_Keeper": {
        "materials.subcontract_orders": ["read"],
    },
    "quality": {
        "materials.subcontract_orders": ["read"],
        "quality.supplier_claim": ["create", "read", "update"],
        "approval.pending": ["read"],
        "approval.initiate": ["read"],
    },
    "org27_pos76": {
        "production.order_wage_lookup": ["read"],
        "production.monthly_capacity_plan": ["read", "manage"],
    },
    # 车间侧可直接调整新排产方案的计划日期与日工时
    "production_supervisor": {
        "production.monthly_capacity_plan": ["read", "manage"],
    },
    "org34_pos91": {
        "production.monthly_capacity_plan": ["read", "manage"],
    },
    "org40_pos91": {
        "production.monthly_capacity_plan": ["read", "manage"],
    },
    "org46_pos91": {
        "production.monthly_capacity_plan": ["read", "manage"],
    },
    "org44_pos97": {
        "production.monthly_capacity_plan": ["read", "manage"],
    },
    "org46_pos97": {
        "production.monthly_capacity_plan": ["read", "manage"],
    },
    "org59_pos97": {
        "production.monthly_capacity_plan": ["read", "manage"],
    },
    "purchase_manager": {
        "materials.task_stock_check": ["read"],
        "materials.inventory_board": ["read"],
        "materials.occupancy": ["read"],
        "quality.supplier_claim": ["read"],
        "approval.pending": ["read"],
        "approval.initiate": ["read"],
    },
    "finance": {
        # 抽检工作台需要读取盘点单列表/详情
        "materials.stock_check": ["read"],
        "materials.stock_check_audit": ["read", "update"],
        "quality.supplier_claim": ["read"],
        "approval.pending": ["read"],
        "approval.initiate": ["read"],
    },
    "general_manager": {
        # 审批详情页需读取索赔单完整单据（复用业务侧纸张视图），与其它审批节点角色一致
        "quality.supplier_claim": ["read"],
        "approval.pending": ["read"],
        "approval.initiate": ["read"],
    },
}


def merge_role_permission_additions(role_code: str, permissions: Dict[str, List[str]] | None) -> Dict[str, List[str]]:
    merged = deepcopy(permissions or {})
    additions = ROLE_PERMISSION_ADDITIONS.get(role_code, {})
    for resource, actions in additions.items():
        current = set(merged.get(resource, []))
        current.update(actions)
        merged[resource] = sorted(current)
    return merged
