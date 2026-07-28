"""采购对外接口

为外部系统（如 WMS / 财务系统）提供采购订单/到料计划查询。
基于 PurchaseOrder 表（po_no + detail_id 唯一）。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.material.purchase_order import PurchaseOrder

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
    "purchase_orders.list",
    "采购订单列表",
    method="GET",
    path="/purchase-orders/list",
    description="采购订单/到料计划列表查询，支持关键字、PO 状态、供应商、ETA 范围、增量同步",
    tags=["采购"],
)
async def purchase_orders_list(ctx: ExternalCallContext) -> dict:
    """采购订单列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（PO 号 / 物料名称 / 订单号 模糊匹配）
        po_status: PO 状态，多选逗号分隔
        supplier_code: 供应商编码精确匹配
        order_no: 关联销售订单号精确匹配
        material_code: 物料编码精确匹配
        eta_start, eta_end: ETA 日期范围 YYYY-MM-DD
        updated_after: 增量同步 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    po_status = params.get("po_status")
    supplier_code = params.get("supplier_code")
    order_no = params.get("order_no")
    material_code = params.get("material_code")
    eta_start = _parse_date(params.get("eta_start"))
    eta_end = _parse_date(params.get("eta_end"))
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(PurchaseOrder)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            PurchaseOrder.po_no.ilike(like_expr),
            PurchaseOrder.material_name.ilike(like_expr),
            PurchaseOrder.order_no.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if po_status:
        statuses = [s.strip() for s in po_status.split(",") if s.strip()]
        if len(statuses) == 1:
            query = query.where(PurchaseOrder.po_status == statuses[0])
        elif statuses:
            query = query.where(PurchaseOrder.po_status.in_(statuses))
        count_query = select(func.count()).select_from(query.subquery())

    if supplier_code:
        query = query.where(PurchaseOrder.supplier_code == supplier_code)
        count_query = select(func.count()).select_from(query.subquery())

    if order_no:
        query = query.where(PurchaseOrder.order_no == order_no)
        count_query = select(func.count()).select_from(query.subquery())

    if material_code:
        query = query.where(PurchaseOrder.material_code == material_code)
        count_query = select(func.count()).select_from(query.subquery())

    if eta_start:
        query = query.where(PurchaseOrder.eta >= eta_start)
        count_query = select(func.count()).select_from(query.subquery())
    if eta_end:
        query = query.where(PurchaseOrder.eta <= eta_end)
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(PurchaseOrder.updated_at >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(PurchaseOrder.po_date.desc().nullslast(), PurchaseOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "po_no": r.po_no,
        "detail_id": r.detail_id,
        "order_no": r.order_no,
        "material_code": r.material_code,
        "material_name": r.material_name,
        "spec_model": r.spec_model,
        "material_type_name": r.material_type_name,
        "supplier_code": r.supplier_code,
        "supplier_name": r.supplier_name,
        "po_qty": float(r.po_qty) if r.po_qty is not None else None,
        "received_qty": float(r.received_qty) if r.received_qty is not None else None,
        "po_price": float(r.po_price) if r.po_price is not None else None,
        "unit": r.unit,
        "po_date": r.po_date.isoformat() if r.po_date else None,
        "po_status": r.po_status,
        "eta": r.eta.isoformat() if r.eta else None,
        "actual_arrival_date": r.actual_arrival_date.isoformat() if r.actual_arrival_date else None,
        "inspection_date": r.inspection_date.isoformat() if r.inspection_date else None,
        "owner": r.owner,
        "is_closed": r.is_closed,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
