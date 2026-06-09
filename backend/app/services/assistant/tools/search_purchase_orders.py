"""Tool: 搜索采购订单 (PO)"""

from typing import Any, Dict
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.purchase_order import PurchaseOrder
from app.services.assistant.tool_registry import register_tool
from app.services.assistant.tools.utils import create_search_result_item

PARAMETERS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，可匹配PO号、关联销售订单号、物料编号、物料名称、供应商名称",
        },
        "po_no": {
            "type": "string",
            "description": "采购订单号（也会同时匹配关联的销售订单号）",
        },
        "order_no": {
            "type": "string",
            "description": "关联的销售订单号（如HJ开头的订单号）",
        },
        "supplier": {
            "type": "string",
            "description": "供应商名称（模糊匹配）",
        },
        "material_code": {
            "type": "string",
            "description": "物料编码",
        },
        "po_status": {
            "type": "string",
            "description": "PO状态",
        },
        "eta_before": {
            "type": "string",
            "description": "预计到货日期截止 YYYY-MM-DD",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限，默认20",
        },
    },
    "required": [],
}


@register_tool(
    name="search_purchase_orders",
    description="搜索采购订单(PO)。支持按PO号、关联销售订单号、供应商、物料编码、PO状态、预计到货日期等条件查询。返回完整的采购订单信息。",
    parameters=PARAMETERS,
    display_name="采购订单查询",
)
async def search_purchase_orders(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    query = select(PurchaseOrder)
    count_query = select(func.count(PurchaseOrder.id))

    filters = []

    keyword = params.get("keyword")
    if keyword:
        like = f"%{keyword}%"
        kw_filter = (
            PurchaseOrder.po_no.ilike(like)
            | PurchaseOrder.order_no.ilike(like)
            | PurchaseOrder.material_code.ilike(like)
            | PurchaseOrder.material_name.ilike(like)
            | PurchaseOrder.supplier_name.ilike(like)
        )
        filters.append(kw_filter)

    po_no = params.get("po_no")
    if po_no:
        # 同时匹配 po_no 和 order_no，因为用户可能混淆采购订单号和销售订单号
        filters.append(
            PurchaseOrder.po_no.ilike(f"%{po_no}%")
            | PurchaseOrder.order_no.ilike(f"%{po_no}%")
        )

    order_no = params.get("order_no")
    if order_no:
        filters.append(PurchaseOrder.order_no.ilike(f"%{order_no}%"))

    supplier = params.get("supplier")
    if supplier:
        filters.append(PurchaseOrder.supplier_name.ilike(f"%{supplier}%"))

    material_code = params.get("material_code")
    if material_code:
        filters.append(PurchaseOrder.material_code.ilike(f"%{material_code}%"))

    po_status = params.get("po_status")
    if po_status:
        filters.append(PurchaseOrder.po_status == po_status)

    eta_before = params.get("eta_before")
    if eta_before:
        try:
            filters.append(PurchaseOrder.eta <= datetime.strptime(eta_before, "%Y-%m-%d").date())
        except ValueError:
            pass

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    limit = params.get("limit")
    if limit:
        query = query.order_by(PurchaseOrder.eta.asc().nullslast()).limit(limit)
    else:
        query = query.order_by(PurchaseOrder.eta.asc().nullslast()).limit(20)
    result = await db.execute(query)
    pos = result.scalars().all()

    items = []
    for po in pos:
        item = create_search_result_item(
            instance=po,
            item_type="purchase_order",
            title=f"PO {po.po_no}",
            subtitle=f"{po.supplier_name or ''} | {po.material_name or ''} | {po.material_code or ''}",
            url=f"/purchase-plan",
            tags=[t for t in [po.po_status] if t],
        )
        items.append(item)

    return {"total": total, "items": items}
