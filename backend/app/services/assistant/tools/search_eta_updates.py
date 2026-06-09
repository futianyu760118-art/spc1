"""Tool: 搜索交期更新(ETA)记录"""

from typing import Any, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order.eta_update import ETAUpdate
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "po_no": {
            "type": "string",
            "description": "采购订单号（模糊匹配）",
        },
        "updater": {
            "type": "string",
            "description": "更新人",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限，默认20",
        },
    },
    "required": [],
}


@register_tool(
    name="search_eta_updates",
    description="搜索交期更新(ETA)记录。可按采购订单号、更新人查询交期变更历史，包含旧交期、新交期、变更原因等信息。",
    parameters=PARAMETERS,
    display_name="交期更新查询",
)
async def search_eta_updates(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    query = select(ETAUpdate)
    count_query = select(func.count(ETAUpdate.id))

    filters = []

    po_no = params.get("po_no")
    if po_no:
        filters.append(ETAUpdate.po_no.ilike(f"%{po_no}%"))

    updater = params.get("updater")
    if updater:
        filters.append(ETAUpdate.updater.ilike(f"%{updater}%"))

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    limit = params.get("limit")
    if limit:
        query = query.order_by(ETAUpdate.created_at.desc()).limit(limit)
    else:
        query = query.order_by(ETAUpdate.created_at.desc())
    result = await db.execute(query)
    rows = result.scalars().all()

    items = []
    for r in rows:
        items.append({
            "type": "eta_update",
            "title": f"交期变更 PO {r.po_no}",
            "subtitle": f"{r.old_eta or '无'} → {r.new_eta} | {r.update_reason or ''}",
            "url": "/purchase-orders",
            "tags": [],
            "po_no": r.po_no,
            "old_eta": str(r.old_eta) if r.old_eta else None,
            "new_eta": str(r.new_eta) if r.new_eta else None,
            "updater": r.updater,
            "update_reason": r.update_reason,
            "remark": r.remark,
            "created_at": str(r.created_at) if r.created_at else None,
        })

    return {"total": total, "items": items}
