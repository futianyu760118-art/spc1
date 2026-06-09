"""Tool: 搜索跑单管理记录"""

from typing import Any, Dict
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order.run_order import RunOrder
from app.services.assistant.tool_registry import register_tool
from app.services.assistant.tools.utils import create_search_result_item

PARAMETERS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，匹配订单号、客户代码",
        },
        "order_no": {
            "type": "string",
            "description": "订单号（模糊匹配）",
        },
        "order_type": {
            "type": "string",
            "enum": ["返单", "新订单", "补单", "配件"],
            "description": "订单性质",
        },
        "order_status": {
            "type": "string",
            "description": "订单状态",
        },
        "is_domestic": {
            "type": "boolean",
            "description": "是否内销跑单",
        },
        "date_start": {
            "type": "string",
            "description": "跑单日期开始 YYYY-MM-DD",
        },
        "date_end": {
            "type": "string",
            "description": "跑单日期结束 YYYY-MM-DD",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限，默认20",
        },
    },
    "required": [],
}


@register_tool(
    name="search_run_orders",
    description="搜索跑单管理记录。支持按订单号、订单性质（返单/新订单/补单/配件）、状态、是否内销、跑单日期范围等条件查询。可查看跑单时间、采购周期、齐套时间、延迟原因等。",
    parameters=PARAMETERS,
    display_name="跑单管理查询",
)
async def search_run_orders(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    query = select(RunOrder)
    count_query = select(func.count(RunOrder.id))

    filters = []

    keyword = params.get("keyword")
    if keyword:
        like = f"%{keyword}%"
        filters.append(
            RunOrder.order_no.ilike(like)
            | RunOrder.customer_code.ilike(like)
        )

    order_no = params.get("order_no")
    if order_no:
        filters.append(RunOrder.order_no.ilike(f"%{order_no}%"))

    order_type = params.get("order_type")
    if order_type:
        filters.append(RunOrder.order_type == order_type)

    order_status = params.get("order_status")
    if order_status:
        filters.append(RunOrder.order_status == order_status)

    is_domestic = params.get("is_domestic")
    if is_domestic is not None:
        filters.append(RunOrder.is_domestic == is_domestic)

    date_start = params.get("date_start")
    if date_start:
        try:
            filters.append(RunOrder.run_date >= datetime.strptime(date_start, "%Y-%m-%d").date())
        except ValueError:
            pass

    date_end = params.get("date_end")
    if date_end:
        try:
            filters.append(RunOrder.run_date <= datetime.strptime(date_end, "%Y-%m-%d").date())
        except ValueError:
            pass

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    limit = params.get("limit")
    if limit:
        query = query.order_by(RunOrder.run_date.desc().nullslast()).limit(limit)
    else:
        query = query.order_by(RunOrder.run_date.desc().nullslast())
    result = await db.execute(query)
    rows = result.scalars().all()

    items = []
    for r in rows:
        item = create_search_result_item(
            instance=r,
            item_type="run_order",
            title=f"跑单 {r.order_no}",
            subtitle=f"{r.customer_code or ''} | {r.order_type or ''} | 跑单日期 {r.run_date or ''}",
            url=f"/run-orders",
            tags=[t for t in [r.order_type, r.order_status] if t],
        )
        items.append(item)

    return {"total": total, "items": items}
