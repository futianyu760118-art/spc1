"""生产对外接口

为外部系统（如 MES / 报工系统）提供生产排产计划查询。
基于 ProductionSchedulePlan 表（按 department + plan_date + order_no + product_code 组织）。
默认只返回当前生效版本（is_active = True）。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.production.schedule_plan import ProductionSchedulePlan

from ..registry import register_external, ExternalCallContext


def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@register_external(
    "schedule_plans.list",
    "生产排产计划列表",
    method="GET",
    path="/schedule-plans/list",
    description="生产排产计划列表查询，支持关键字、部门、状态、订单号、排产日期范围、增量同步（默认只返回生效版本）",
    tags=["生产"],
)
async def schedule_plans_list(ctx: ExternalCallContext) -> dict:
    """生产排产计划列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（订单号 / 产品编码 模糊匹配）
        department: 部门精确匹配
        status: 计划状态，多选逗号分隔 (planned/confirmed/locked/in_progress/done/...)
        order_no: 订单号精确匹配
        product_code: 产品编码精确匹配
        plan_date_start, plan_date_end: 排产日期范围 YYYY-MM-DD
        include_inactive: 是否包含历史版本 (1-是 0-否，默认 0 只返回 is_active=True)
        updated_after: 增量同步 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    department = params.get("department")
    status = params.get("status")
    order_no = params.get("order_no")
    product_code = params.get("product_code")
    plan_date_start = _parse_date(params.get("plan_date_start"))
    plan_date_end = _parse_date(params.get("plan_date_end"))
    include_inactive = str(params.get("include_inactive", "0")) in ("1", "true", "True")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(ProductionSchedulePlan)
    if not include_inactive:
        query = query.where(ProductionSchedulePlan.is_active == True)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            ProductionSchedulePlan.order_no.ilike(like_expr),
            ProductionSchedulePlan.product_code.ilike(like_expr),
            ProductionSchedulePlan.model_code.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if department:
        query = query.where(ProductionSchedulePlan.department == department)
        count_query = select(func.count()).select_from(query.subquery())

    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            query = query.where(ProductionSchedulePlan.status == statuses[0])
        elif statuses:
            query = query.where(ProductionSchedulePlan.status.in_(statuses))
        count_query = select(func.count()).select_from(query.subquery())

    if order_no:
        query = query.where(ProductionSchedulePlan.order_no == order_no)
        count_query = select(func.count()).select_from(query.subquery())

    if product_code:
        query = query.where(ProductionSchedulePlan.product_code == product_code)
        count_query = select(func.count()).select_from(query.subquery())

    if plan_date_start:
        query = query.where(ProductionSchedulePlan.plan_date >= plan_date_start)
        count_query = select(func.count()).select_from(query.subquery())
    if plan_date_end:
        query = query.where(ProductionSchedulePlan.plan_date <= plan_date_end)
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(ProductionSchedulePlan.updated_at >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(
            ProductionSchedulePlan.plan_date.desc(),
            ProductionSchedulePlan.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "department": r.department,
        "plan_date": r.plan_date.isoformat() if r.plan_date else None,
        "order_no": r.order_no,
        "line_no": r.line_no,
        "product_code": r.product_code,
        "model_code": r.model_code,
        "quantity": float(r.quantity) if r.quantity is not None else None,
        "owner": r.owner,
        "start_date": r.start_date.isoformat() if r.start_date else None,
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "priority": r.priority,
        "status": r.status,
        "upph": float(r.upph) if r.upph is not None else None,
        "plan_version": r.plan_version,
        "is_active": r.is_active,
        "confirmed_by": r.confirmed_by,
        "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
