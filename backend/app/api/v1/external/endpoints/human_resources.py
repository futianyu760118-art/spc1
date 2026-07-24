"""组织人员对外接口

为外部系统提供组织架构、岗位、员工信息查询。
区别于内部 /api/v1/basicdata/* 的 CRUD 逻辑，对外只暴露精简字段集与常用筛选条件。
"""

from datetime import datetime
from typing import Optional, List, Set

from sqlalchemy import select, func, or_, cast, String
from sqlalchemy.orm import aliased

from app.models.basicdata.organization import Organization
from app.models.basicdata.position import Position
from app.models.basicdata.employee import Employee
from app.models.basicdata.employee_organization import EmployeeOrganization

from ..registry import register_external, ExternalCallContext


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _mask_phone(v):
    if not v or len(v) < 7:
        return v
    return v[:3] + "****" + v[-4:]


# ═══════════════════════════════════════════
# 组织
# ═══════════════════════════════════════════

@register_external(
    "organizations.list",
    "组织列表",
    method="GET",
    path="/organizations/list",
    description="组织架构列表查询，支持关键字、组织类型、状态筛选",
    tags=["组织人员"],
)
async def organizations_list(ctx: ExternalCallContext) -> dict:
    """组织列表（外部定制版）

    参数（query）:
        page, page_size: 分页
        keyword: 关键字（oa_org_id / org_name 模糊匹配）
        org_type: 组织类型精确匹配
        status: 状态，多选逗号分隔 (1-启用 0-禁用)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    org_type = params.get("org_type")
    status = params.get("status")

    query = select(Organization)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Organization.oa_org_id.ilike(like_expr),
            Organization.org_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if org_type:
        query = query.where(Organization.org_type == org_type)
        count_query = select(func.count()).select_from(query.subquery())

    if status is not None and status != "":
        statuses = [s.strip() for s in str(status).split(",") if s.strip() != ""]
        if len(statuses) == 1:
            query = query.where(Organization.status == int(statuses[0]))
        elif statuses:
            query = query.where(Organization.status.in_([int(s) for s in statuses]))
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    ParentOrg = aliased(Organization)
    LeaderEmp = aliased(Employee)

    query = (
        query
        .outerjoin(ParentOrg, Organization.parent_id == ParentOrg.id)
        .outerjoin(LeaderEmp, Organization.leader_id == LeaderEmp.id)
        .add_columns(
            ParentOrg.oa_org_id.label("parent_code"),
            LeaderEmp.emp_name.label("leader_name"),
        )
        .order_by(Organization.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    items = []
    for row in rows:
        org = row[0]
        parent_code = row.parent_code
        leader_name = row.leader_name
        items.append({
            "oa_org_id": org.oa_org_id,
            "org_name": org.org_name,
            "org_type": org.org_type,
            "parent_code": parent_code,
            "leader_name": leader_name,
            "status": org.status,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ═══════════════════════════════════════════
# 岗位
# ═══════════════════════════════════════════

@register_external(
    "positions.list",
    "岗位列表",
    method="GET",
    path="/positions/list",
    description="岗位列表查询，支持关键字、状态筛选",
    tags=["组织人员"],
)
async def positions_list(ctx: ExternalCallContext) -> dict:
    """岗位列表（外部定制版）

    参数（query）:
        page, page_size: 分页
        keyword: 关键字（position_code / position_name 模糊匹配）
        status: 状态，多选逗号分隔 (1-启用 0-禁用)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    status = params.get("status")

    query = select(Position)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Position.position_code.ilike(like_expr),
            Position.position_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if status is not None and status != "":
        statuses = [s.strip() for s in str(status).split(",") if s.strip() != ""]
        if len(statuses) == 1:
            query = query.where(Position.status == int(statuses[0]))
        elif statuses:
            query = query.where(Position.status.in_([int(s) for s in statuses]))
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query
        .order_by(Position.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "position_code": r.position_code,
        "position_name": r.position_name,
        "status": r.status,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ═══════════════════════════════════════════
# 员工
# ═══════════════════════════════════════════

@register_external(
    "employees.list",
    "员工列表",
    method="GET",
    path="/employees/list",
    description="员工列表查询，支持关键字、组织、岗位、状态筛选（手机号脱敏）",
    tags=["组织人员"],
)
async def employees_list(ctx: ExternalCallContext) -> dict:
    """员工列表（外部定制版）

    参数（query）:
        page, page_size: 分页
        keyword: 关键字（oa_user_id / emp_name 模糊匹配）
        org_id: 组织 oa_org_id 筛选
        position_code: 岗位编码筛选
        status: 状态，多选逗号分隔
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    org_id = params.get("org_id")
    position_code = params.get("position_code")
    status = params.get("status")

    query = select(Employee)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Employee.oa_user_id.ilike(like_expr),
            Employee.emp_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if org_id:
        query = query.where(Employee.org_id == org_id)
        count_query = select(func.count()).select_from(query.subquery())

    if position_code:
        PosFilter = aliased(Position)
        query = query.join(PosFilter, Employee.position_id == PosFilter.id)
        query = query.where(PosFilter.position_code == position_code)
        count_query = select(func.count()).select_from(query.subquery())

    if status is not None and status != "":
        statuses = [s.strip() for s in str(status).split(",") if s.strip() != ""]
        if len(statuses) == 1:
            query = query.where(Employee.status == int(statuses[0]))
        elif statuses:
            query = query.where(Employee.status.in_([int(s) for s in statuses]))
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    OrgAlias = aliased(Organization)
    PosAlias = aliased(Position)

    query = (
        query
        .outerjoin(OrgAlias, cast(Employee.org_id, String) == OrgAlias.oa_org_id)
        .outerjoin(PosAlias, Employee.position_id == PosAlias.id)
        .add_columns(
            OrgAlias.org_name.label("org_name"),
            PosAlias.position_name.label("pos_name"),
        )
        .order_by(Employee.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    items = []
    for row in rows:
        emp = row[0]
        items.append({
            "id": emp.id,
            "oa_user_id": emp.oa_user_id,
            "emp_name": emp.emp_name,
            "org_id": emp.org_id,
            "org_name": row.org_name,
            "position_name": row.pos_name or emp.position,
            "phone": _mask_phone(emp.phone),
            "email": emp.email,
            "status": emp.status,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ═══════════════════════════════════════════
# 组织下员工
# ═══════════════════════════════════════════

async def _get_descendant_org_codes(db, root_oa_org_id: str) -> Set[str]:
    """递归获取某组织及其所有子组织的 org_code 集合"""
    result = set()
    to_process = [root_oa_org_id]
    processed_ids = set()

    while to_process:
        current = to_process.pop()
        res = await db.execute(
            select(Organization.org_code, Organization.id)
            .where(Organization.oa_org_id == current)
        )
        row = res.first()
        if not row or row[1] in processed_ids:
            continue
        org_code, org_id = row[0], row[1]
        processed_ids.add(org_id)
        result.add(org_code)

        child_res = await db.execute(
            select(Organization.oa_org_id)
            .where(Organization.parent_id == org_id)
        )
        for child_row in child_res.all():
            to_process.append(child_row[0])

    return result


@register_external(
    "organizations.employees",
    "组织员工",
    method="GET",
    path="/organizations/{oa_org_id}/employees",
    description="查询指定组织（含子组织）下的员工列表",
    tags=["组织人员"],
)
async def organization_employees(ctx: ExternalCallContext) -> dict:
    """组织下员工列表（外部定制版）

    路径参数:
        oa_org_id: 组织 oa_org_id

    查询参数:
        page, page_size: 分页
        keyword: 关键字（oa_user_id / emp_name 模糊匹配）
        position_code: 岗位编码筛选
        status: 状态，多选逗号分隔
    """
    params = ctx.params
    db = ctx.db
    oa_org_id = params.get("oa_org_id")

    if not oa_org_id:
        return {"items": [], "total": 0, "page": 1, "page_size": 20}

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    position_code = params.get("position_code")
    status = params.get("status")

    org_codes = await _get_descendant_org_codes(db, oa_org_id)

    if not org_codes:
        return {"items": [], "total": 0, "page": 1, "page_size": page_size}

    # 批量获取 org_code 对应的 oa_org_id（避免 N+1）
    org_rows = (await db.execute(
        select(Organization.oa_org_id)
        .where(Organization.org_code.in_(org_codes))
    )).all()
    descendant_oa_ids = {int(row[0]) for row in org_rows if row[0]}

    # 同时收集所有 org_codes 对应的 oa_org_id
    all_oa_ids = set(descendant_oa_ids)

    # 员工查询：主部门匹配 oa_org_id，或兼职关联 org_code
    query = (
        select(Employee)
        .distinct()
    )
    count_query_base = select(Employee).distinct()

    if all_oa_ids:
        sub_emp = (
            select(EmployeeOrganization.emp_code)
            .where(EmployeeOrganization.org_code.in_(org_codes))
        )
        query = query.where(
            or_(
                Employee.org_id.in_(all_oa_ids),
                Employee.emp_code.in_(sub_emp),
            )
        )
        count_query_base = count_query_base.where(
            or_(
                Employee.org_id.in_(all_oa_ids),
                Employee.emp_code.in_(sub_emp),
            )
        )

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Employee.oa_user_id.ilike(like_expr),
            Employee.emp_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query_base = count_query_base.where(kw_cond)

    if position_code:
        PosFilter = aliased(Position)
        query = query.join(PosFilter, Employee.position_id == PosFilter.id)
        query = query.where(PosFilter.position_code == position_code)
        count_query_base = count_query_base.join(PosFilter, Employee.position_id == PosFilter.id)
        count_query_base = count_query_base.where(PosFilter.position_code == position_code)

    if status is not None and status != "":
        statuses = [s.strip() for s in str(status).split(",") if s.strip() != ""]
        if len(statuses) == 1:
            query = query.where(Employee.status == int(statuses[0]))
            count_query_base = count_query_base.where(Employee.status == int(statuses[0]))
        elif statuses:
            query = query.where(Employee.status.in_([int(s) for s in statuses]))
            count_query_base = count_query_base.where(Employee.status.in_([int(s) for s in statuses]))

    count_query = select(func.count()).select_from(count_query_base.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    OrgAlias = aliased(Organization)
    PosAlias = aliased(Position)

    query = (
        query
        .outerjoin(OrgAlias, cast(Employee.org_id, String) == OrgAlias.oa_org_id)
        .outerjoin(PosAlias, Employee.position_id == PosAlias.id)
        .add_columns(
            OrgAlias.org_name.label("org_name"),
            PosAlias.position_name.label("pos_name"),
        )
        .order_by(Employee.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    items = []
    for row in rows:
        emp = row[0]
        items.append({
            "id": emp.id,
            "oa_user_id": emp.oa_user_id,
            "emp_name": emp.emp_name,
            "org_id": emp.org_id,
            "org_name": row.org_name,
            "position_name": row.pos_name or emp.position,
            "phone": _mask_phone(emp.phone),
            "email": emp.email,
            "status": emp.status,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}
