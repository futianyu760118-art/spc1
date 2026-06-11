"""Position-driven role helpers for user permissions."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha1
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.employee import Employee
from app.models.basicdata.position import Position
from app.models.basicdata.user import SysRole, SysUser


READ = ["read"]
READ_UPDATE = ["read", "update"]
READ_WRITE = ["create", "read", "update"]
FULL = ["create", "read", "update", "delete"]
FULL_IMPORT = ["create", "read", "update", "delete", "import"]
READ_UPDATE_IMPORT = ["read", "update", "import"]

COMMON_INTERNAL_PERMISSIONS = {
    "dashboard": READ,
    "basicdata.feedback": ["create", "read"],
    "announcements": READ,
    "topbar.share": READ,
    "topbar.feedback": READ,
    "topbar.ai_search": READ,
    "topbar.font_size": READ,
    "topbar.notifications": READ,
}


def _merge_permissions(*parts: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {}
    for part in parts:
        for resource, actions in part.items():
            merged.setdefault(resource, set()).update(actions)
    return {resource: sorted(actions) for resource, actions in merged.items()}


POSITION_PERMISSION_PRESETS: dict[str, dict[str, list[str]]] = {
    "employee": _merge_permissions(COMMON_INTERNAL_PERMISSIONS),
    "readonly": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ,
            "orders.run_orders": READ,
            "orders.risk_pool": READ,
            "materials.purchase_plan": READ,
            "materials.issues": READ,
            "materials.long_lead": READ,
            "materials.kit_analysis": READ,
            "materials.supplier_risk": READ,
            "production.overview": READ,
            "production.front_process": READ,
            "production.smt": READ,
            "production.lean": READ,
            "production.assembly": READ,
            "production.packaging": READ,
            "production.exceptions": READ,
            "exceptions.pool": READ,
            "exceptions.issue_log": READ,
            "exceptions.change_log": READ,
            "exceptions.quality": READ,
            "exceptions.product_samples": READ,
            "exceptions.closure": READ,
            "rules.order_standards": READ,
            "rules.work_instructions": READ,
        },
    ),
    "operator": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "production.overview": READ,
            "production.front_process": READ_UPDATE,
            "production.smt": READ_UPDATE,
            "production.lean": READ_UPDATE,
            "production.assembly": READ_UPDATE,
            "production.packaging": READ_UPDATE,
            "production.exceptions": READ_WRITE,
            "rules.work_instructions": READ,
        },
    ),
    "production_lead": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ,
            "orders.run_orders": READ_UPDATE,
            "materials.kit_analysis": READ,
            "production.overview": READ_UPDATE,
            "production.front_process": READ_UPDATE_IMPORT,
            "production.smt": READ_UPDATE_IMPORT,
            "production.lean": READ_UPDATE_IMPORT,
            "production.assembly": READ_UPDATE_IMPORT,
            "production.packaging": READ_UPDATE_IMPORT,
            "production.exceptions": READ_WRITE,
            "exceptions.pool": READ_UPDATE,
            "exceptions.issue_log": READ_WRITE,
            "exceptions.closure": READ_UPDATE,
            "rules.order_standards": READ,
            "rules.work_instructions": READ,
            "basicdata.data": READ,
        },
    ),
    "quality": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "production.overview": READ,
            "production.front_process": READ,
            "production.smt": READ,
            "production.lean": READ,
            "production.assembly": READ,
            "production.packaging": READ,
            "production.exceptions": READ_UPDATE,
            "exceptions.pool": READ,
            "exceptions.issue_log": READ_WRITE,
            "exceptions.quality": ["create", "read", "update", "import"],
            "exceptions.product_samples": READ_UPDATE,
            "exceptions.closure": READ_UPDATE,
            "rules.inspection": READ,
            "rules.node_standards": READ,
            "rules.order_standards": READ,
            "rules.work_instructions": READ,
            "basicdata.data": READ,
        },
    ),
    "quality_manager": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ,
            "production.overview": READ_UPDATE,
            "production.exceptions": READ_UPDATE,
            "exceptions.pool": READ_UPDATE,
            "exceptions.issue_log": READ_UPDATE,
            "exceptions.change_log": READ_UPDATE,
            "exceptions.quality": FULL_IMPORT,
            "exceptions.product_samples": FULL,
            "exceptions.closure": READ_UPDATE,
            "rules.inspection": READ_UPDATE,
            "rules.node_standards": READ_UPDATE,
            "rules.order_standards": READ,
            "rules.work_instructions": READ,
            "basicdata.data": READ,
            "audit": READ,
        },
    ),
    "engineer": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ,
            "materials.kit_analysis": READ,
            "production.overview": READ_UPDATE,
            "production.front_process": READ_UPDATE,
            "production.smt": READ_UPDATE,
            "production.lean": READ_UPDATE,
            "production.assembly": READ_UPDATE,
            "production.packaging": READ_UPDATE,
            "production.exceptions": READ_WRITE,
            "exceptions.pool": READ_UPDATE,
            "exceptions.issue_log": READ_WRITE,
            "exceptions.change_log": READ_UPDATE,
            "exceptions.quality": READ_UPDATE,
            "exceptions.product_samples": READ_UPDATE,
            "exceptions.closure": READ_UPDATE,
            "npi": READ_UPDATE,
            "rules.inspection": READ_UPDATE,
            "rules.node_standards": READ_UPDATE,
            "rules.order_standards": READ_UPDATE,
            "rules.work_instructions": READ_UPDATE,
            "basicdata.data": READ,
        },
    ),
    "technician": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "production.overview": READ,
            "production.front_process": READ_UPDATE,
            "production.smt": READ_UPDATE,
            "production.lean": READ_UPDATE,
            "production.assembly": READ_UPDATE,
            "production.packaging": READ_UPDATE,
            "production.exceptions": READ_WRITE,
            "exceptions.issue_log": READ_WRITE,
            "exceptions.quality": READ,
            "rules.work_instructions": READ,
            "basicdata.data": READ,
        },
    ),
    "sales": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ_UPDATE,
            "orders.run_orders": READ_UPDATE,
            "orders.risk_pool": READ,
            "materials.purchase_plan": READ,
            "materials.kit_analysis": READ,
            "materials.supplier_risk": READ,
            "exceptions.pool": READ,
            "exceptions.issue_log": READ_WRITE,
            "exceptions.change_log": READ,
            "exceptions.closure": READ,
            "meetings": READ_UPDATE,
            "npi": READ,
            "basicdata.data": READ,
        },
    ),
    "purchaser": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ,
            "orders.run_orders": READ,
            "orders.risk_pool": READ,
            "materials.purchase_plan": ["create", "read", "update", "import"],
            "materials.issues": ["create", "read", "update", "import"],
            "materials.long_lead": ["create", "read", "update", "import"],
            "materials.kit_analysis": ["create", "read", "update", "import"],
            "materials.supplier_risk": ["create", "read", "update", "import"],
            "materials.supplier_payment": ["create", "read", "update", "import"],
            "exceptions.pool": READ,
            "exceptions.issue_log": READ,
            "exceptions.change_log": READ,
            "exceptions.quality": READ,
            "exceptions.closure": READ,
            "meetings": READ,
            "npi": READ,
            "basicdata.import": READ,
            "basicdata.data": READ,
            "audit": READ,
        },
    ),
    "warehouse": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ,
            "materials.purchase_plan": READ_UPDATE_IMPORT,
            "materials.issues": READ_UPDATE_IMPORT,
            "materials.long_lead": READ,
            "materials.kit_analysis": READ_UPDATE_IMPORT,
            "production.overview": READ,
            "basicdata.data": READ,
        },
    ),
    "finance": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ,
            "materials.purchase_plan": READ,
            "materials.supplier_risk": READ,
            "materials.supplier_payment": ["create", "read", "update", "import"],
            "basicdata.data": READ,
            "audit": READ,
        },
    ),
    "hr_admin": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "basicdata.data": READ_UPDATE,
            "users": READ_UPDATE,
            "audit": READ,
            "announcements": READ_WRITE,
        },
    ),
    "assistant": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ,
            "orders.run_orders": READ,
            "materials.purchase_plan": READ,
            "materials.kit_analysis": READ,
            "production.overview": READ,
            "exceptions.pool": READ,
            "exceptions.issue_log": READ_WRITE,
            "meetings": READ_UPDATE,
            "basicdata.data": READ,
        },
    ),
    "manager": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ_UPDATE,
            "orders.run_orders": READ_UPDATE,
            "orders.risk_pool": READ_UPDATE,
            "materials.purchase_plan": READ_UPDATE,
            "materials.issues": READ_UPDATE,
            "materials.long_lead": READ_UPDATE,
            "materials.kit_analysis": READ_UPDATE,
            "materials.supplier_risk": READ_UPDATE,
            "materials.supplier_payment": READ_UPDATE,
            "production.overview": READ_UPDATE,
            "production.front_process": READ_UPDATE,
            "production.smt": READ_UPDATE,
            "production.lean": READ_UPDATE,
            "production.assembly": READ_UPDATE,
            "production.packaging": READ_UPDATE,
            "production.exceptions": READ_UPDATE,
            "exceptions.pool": READ_UPDATE,
            "exceptions.issue_log": READ_UPDATE,
            "exceptions.change_log": READ_UPDATE,
            "exceptions.quality": READ_UPDATE,
            "exceptions.product_samples": READ_UPDATE,
            "exceptions.closure": READ_UPDATE,
            "meetings": FULL,
            "npi": READ_UPDATE,
            "rules.order_standards": READ_UPDATE,
            "rules.work_instructions": READ_UPDATE,
            "basicdata.import": READ,
            "basicdata.data": READ,
            "basicdata.feedback": READ_UPDATE,
            "audit": READ,
        },
    ),
    "director": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ_UPDATE,
            "orders.run_orders": READ_UPDATE,
            "orders.risk_pool": READ_UPDATE,
            "materials.purchase_plan": READ_UPDATE,
            "materials.issues": READ_UPDATE,
            "materials.long_lead": READ_UPDATE,
            "materials.kit_analysis": READ_UPDATE,
            "materials.supplier_risk": READ_UPDATE,
            "materials.supplier_payment": READ_UPDATE,
            "production.overview": READ_UPDATE,
            "production.front_process": READ,
            "production.smt": READ,
            "production.lean": READ,
            "production.assembly": READ,
            "production.packaging": READ,
            "production.exceptions": READ_UPDATE,
            "exceptions.pool": READ_UPDATE,
            "exceptions.issue_log": READ_UPDATE,
            "exceptions.change_log": READ_UPDATE,
            "exceptions.quality": READ_UPDATE,
            "exceptions.product_samples": READ_UPDATE,
            "exceptions.closure": READ_UPDATE,
            "meetings": FULL,
            "npi": READ_UPDATE,
            "rules.risk_rules": READ,
            "rules.inspection": READ,
            "rules.node_standards": READ,
            "rules.order_standards": READ,
            "rules.work_instructions": READ,
            "rules.responsibility": READ,
            "rules.status_dict": READ,
            "basicdata.import": READ,
            "basicdata.data": READ,
            "basicdata.feedback": READ_UPDATE,
            "audit": READ,
        },
    ),
    "executive": _merge_permissions(
        COMMON_INTERNAL_PERMISSIONS,
        {
            "orders.list": READ_UPDATE,
            "orders.run_orders": READ_UPDATE,
            "orders.risk_pool": READ_UPDATE,
            "materials.purchase_plan": READ_UPDATE,
            "materials.issues": READ_UPDATE,
            "materials.long_lead": READ_UPDATE,
            "materials.kit_analysis": READ_UPDATE,
            "materials.supplier_risk": READ_UPDATE,
            "materials.supplier_payment": READ_UPDATE,
            "production.overview": READ_UPDATE,
            "production.front_process": READ,
            "production.smt": READ,
            "production.lean": READ,
            "production.assembly": READ,
            "production.packaging": READ,
            "production.exceptions": READ_UPDATE,
            "exceptions.pool": READ_UPDATE,
            "exceptions.issue_log": READ_UPDATE,
            "exceptions.change_log": READ_UPDATE,
            "exceptions.quality": READ_UPDATE,
            "exceptions.product_samples": READ_UPDATE,
            "exceptions.closure": READ_UPDATE,
            "meetings": FULL,
            "npi": READ_UPDATE,
            "rules.risk_rules": READ_UPDATE,
            "rules.inspection": READ_UPDATE,
            "rules.node_standards": READ_UPDATE,
            "rules.order_standards": READ_UPDATE,
            "rules.work_instructions": READ_UPDATE,
            "rules.responsibility": READ_UPDATE,
            "rules.status_dict": READ_UPDATE,
            "basicdata.import": READ,
            "basicdata.data": READ,
            "basicdata.feedback": READ_UPDATE,
            "announcements": READ_WRITE,
            "audit": READ,
            "settings": READ,
        },
    ),
    "facility": _merge_permissions(COMMON_INTERNAL_PERMISSIONS),
}

POSITION_CATEGORY_BY_NAME = {
    "压铸师傅": "production_lead",
    "制程检验员": "quality",
    "组长": "production_lead",
    "模具师傅": "technician",
    "工程师": "engineer",
    "实验室测量员": "quality",
    "业务员": "sales",
    "设备技术员": "technician",
    "抛丸工": "operator",
    "经理": "manager",
    "顾问": "readonly",
    "总监": "director",
    "技术员": "technician",
    "门卫": "facility",
    "厨师": "facility",
    "总经理助理": "assistant",
    "专员": "assistant",
    "维修技术员": "technician",
    "普工": "operator",
    "人事行政主管": "hr_admin",
    "主任": "production_lead",
    "首件员": "quality",
    "喷枪手": "operator",
    "主管": "manager",
    "电子工程师": "engineer",
    "仓管员": "warehouse",
    "多能工": "operator",
    "模具学徒工": "operator",
    "品质主管": "quality_manager",
    "助理工程师": "engineer",
    "结构工程师": "engineer",
    "保洁": "facility",
    "采购员": "purchaser",
    "助理": "assistant",
    "总经理": "executive",
    "主办会计": "finance",
    "AI经理": "manager",
    "后勤": "facility",
    "副总": "director",
    "压铸工": "operator",
    "成本会计": "finance",
    "开发工程师": "engineer",
}


def get_position_category(position_name: Optional[str]) -> str:
    name = (position_name or "").strip()
    if name in POSITION_CATEGORY_BY_NAME:
        return POSITION_CATEGORY_BY_NAME[name]
    if "总经理" in name:
        return "executive"
    if "总监" in name or "副总" in name:
        return "director"
    if "经理" in name or "主管" in name or "主任" in name:
        return "manager"
    if "品质" in name or "检验" in name or "测量" in name or "首件" in name:
        return "quality"
    if "采购" in name:
        return "purchaser"
    if "会计" in name or "财务" in name or "成本" in name:
        return "finance"
    if "仓" in name:
        return "warehouse"
    if "工程师" in name or "工程" in name or "开发" in name:
        return "engineer"
    if "技术" in name or "维修" in name or "设备" in name or "模具" in name:
        return "technician"
    if "业务" in name or "销售" in name:
        return "sales"
    if "保洁" in name or "厨师" in name or "门卫" in name or "后勤" in name:
        return "facility"
    if "工" in name or "喷枪" in name or "抛丸" in name:
        return "operator"
    return "employee"


def get_position_permissions(position_name: Optional[str]) -> dict[str, list[str]]:
    category = get_position_category(position_name)
    return deepcopy(POSITION_PERMISSION_PRESETS.get(category, POSITION_PERMISSION_PRESETS["employee"]))


def make_position_role_code(position_code: Optional[str], position_name: Optional[str]) -> str:
    source = (position_name or position_code or "position").strip().lower()
    digest = sha1(source.encode("utf-8")).hexdigest()[:24]
    return f"pos_{digest}"


def make_position_role_name(position_name: Optional[str]) -> str:
    name = (position_name or "未命名岗位").strip()
    return f"岗位-{name}"


async def ensure_position_role(db: AsyncSession, position: Position) -> tuple[SysRole, bool, bool]:
    """Ensure a role exists for a position.

    Returns (role, role_created, position_linked).
    Existing non-empty permissions are preserved so administrators can tune them.
    """
    desired_name = make_position_role_name(position.position_name)
    if position.role_id:
        role_result = await db.execute(select(SysRole).where(SysRole.id == position.role_id))
        role = role_result.scalar_one_or_none()
        if role:
            if role.role_name != desired_name:
                role.role_name = desired_name
            if not role.permissions:
                role.permissions = get_position_permissions(position.position_name)
            return role, False, False

    role_code = make_position_role_code(position.position_code, position.position_name)
    role_result = await db.execute(select(SysRole).where(SysRole.role_code == role_code))
    role = role_result.scalar_one_or_none()
    role_created = False
    if role:
        if role.role_name != desired_name:
            role.role_name = desired_name
        if not role.permissions:
            role.permissions = get_position_permissions(position.position_name)
    else:
        role = SysRole(
            role_code=role_code,
            role_name=desired_name,
            permissions=get_position_permissions(position.position_name),
        )
        db.add(role)
        await db.flush()
        role_created = True

    linked = position.role_id != role.id
    position.role_id = role.id
    return role, role_created, linked


async def resolve_position_for_employee(db: AsyncSession, employee: Employee) -> Optional[Position]:
    if employee.position_id:
        result = await db.execute(select(Position).where(Position.id == employee.position_id))
        position = result.scalar_one_or_none()
        if position:
            return position

    position_name = (employee.position or "").strip()
    if not position_name:
        return None

    result = await db.execute(select(Position).where(Position.position_name == position_name))
    positions = result.scalars().all()
    if len(positions) == 1:
        employee.position_id = positions[0].id
        return positions[0]
    return None


async def resolve_role_for_employee(db: AsyncSession, employee: Employee) -> tuple[Optional[SysRole], Optional[Position]]:
    position = await resolve_position_for_employee(db, employee)
    if not position:
        return None, None
    role, _, _ = await ensure_position_role(db, position)
    return role, position


async def resolve_employee_role_by_code(
    db: AsyncSession,
    emp_code: str,
) -> tuple[Optional[Employee], Optional[Position], Optional[SysRole]]:
    clean_code = (emp_code or "").strip()
    if not clean_code:
        return None, None, None
    result = await db.execute(select(Employee).where(Employee.emp_code == clean_code))
    employee = result.scalar_one_or_none()
    if not employee:
        return None, None, None
    role, position = await resolve_role_for_employee(db, employee)
    return employee, position, role


async def sync_user_role_from_employee(db: AsyncSession, employee: Employee) -> bool:
    role, _ = await resolve_role_for_employee(db, employee)
    if not role:
        return False
    result = await db.execute(select(SysUser).where(SysUser.emp_code == employee.emp_code))
    user = result.scalar_one_or_none()
    if not user:
        return False
    if user.role_id == role.id:
        return False
    user.role_id = role.id
    return True
