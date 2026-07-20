"""生产任务单对外接口

为外部系统定制的 OA 生产任务单查询接口。基于 ProductionTaskOrder 表。
支持分页、关键字、车间、类型、状态、增量同步。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.production.production_task_order import ProductionTaskOrder

from ..registry import register_external, ExternalCallContext


def _parse_int(s: Optional[str]) -> Optional[int]:
    if s is None or s == "":
        return None
    try:
        return int(s)
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
    "production_task_orders.list",
    "生产任务单列表",
    method="GET",
    path="/production-task-orders/list",
    description="OA 生产任务单列表查询，支持关键字、车间、类型、状态、增量同步",
    tags=["生产"],
)
async def production_task_orders_list(ctx: ExternalCallContext) -> dict:
    """生产任务单列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（任务单号 / 物料名称 模糊匹配）
        workshop: 生产车间精确匹配
        task_type: 类型精确匹配
        is_closed: 是否关闭 0/1
        audit_status: 审核状态 0=未审核 1=已审核
        mrp_flag: MRP标志 0/1
        sale_order_no: 销售订单号精确匹配
        updated_after: 增量同步，仅返回 updated_at >= 此时间的记录 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    workshop = params.get("workshop")
    task_type = params.get("task_type")
    is_closed = _parse_int(params.get("is_closed"))
    audit_status = _parse_int(params.get("audit_status"))
    mrp_flag = _parse_int(params.get("mrp_flag"))
    sale_order_no = params.get("sale_order_no")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(ProductionTaskOrder)
    count_query = select(func.count()).select_from(ProductionTaskOrder)

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            ProductionTaskOrder.task_no.ilike(like_expr),
            ProductionTaskOrder.material_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = count_query.where(kw_cond)

    if workshop:
        query = query.where(ProductionTaskOrder.workshop == workshop)
        count_query = count_query.where(ProductionTaskOrder.workshop == workshop)

    if task_type:
        query = query.where(ProductionTaskOrder.task_type == task_type)
        count_query = count_query.where(ProductionTaskOrder.task_type == task_type)

    if is_closed is not None:
        query = query.where(ProductionTaskOrder.is_closed == is_closed)
        count_query = count_query.where(ProductionTaskOrder.is_closed == is_closed)

    if audit_status is not None:
        query = query.where(ProductionTaskOrder.audit_status == audit_status)
        count_query = count_query.where(ProductionTaskOrder.audit_status == audit_status)

    if mrp_flag is not None:
        query = query.where(ProductionTaskOrder.mrp_flag == mrp_flag)
        count_query = count_query.where(ProductionTaskOrder.mrp_flag == mrp_flag)

    if sale_order_no:
        query = query.where(ProductionTaskOrder.sale_order_no == sale_order_no)
        count_query = count_query.where(ProductionTaskOrder.sale_order_no == sale_order_no)

    if updated_after:
        query = query.where(ProductionTaskOrder.updated_at >= updated_after)
        count_query = count_query.where(ProductionTaskOrder.updated_at >= updated_after)

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(ProductionTaskOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "task_id": r.task_id,
        "task_no": r.task_no,
        "workshop": r.workshop,
        "material_code": r.material_code,
        "material_name": r.material_name,
        "planned_start_date": r.planned_start_date.isoformat() if r.planned_start_date else None,
        "planned_end_date": r.planned_end_date.isoformat() if r.planned_end_date else None,
        "actual_start_date": r.actual_start_date.isoformat() if r.actual_start_date else None,
        "actual_end_date": r.actual_end_date.isoformat() if r.actual_end_date else None,
        "task_qty": float(r.task_qty) if r.task_qty is not None else None,
        "repair_qty": float(r.repair_qty) if r.repair_qty is not None else None,
        "actual_qty": float(r.actual_qty) if r.actual_qty is not None else None,
        "task_type": r.task_type,
        "sale_order_no": r.sale_order_no,
        "sale_order_id": r.sale_order_id,
        "start_flag": r.start_flag,
        "is_closed": r.is_closed,
        "audit_status": r.audit_status,
        "mrp_flag": r.mrp_flag,
        "audit_user_id": r.audit_user_id,
        "request_user_id": r.request_user_id,
        "supplier_id": r.supplier_id,
        "erp_updated_at": r.erp_updated_at.isoformat() if r.erp_updated_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
