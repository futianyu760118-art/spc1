"""Tool: 搜索销售订单"""

from typing import Any, Dict
from datetime import date, datetime, timedelta

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order.sale_order import SaleOrder
from app.services.assistant.tool_registry import register_tool
from app.services.assistant.tools.utils import create_search_result_item

PARAMETERS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，可匹配订单号、客户名、产品名",
        },
        "customer": {
            "type": "string",
            "description": "客户名称（模糊匹配）",
        },
        "order_no": {
            "type": "string",
            "description": "订单号（精确或模糊）",
        },
        "risk_level": {
            "type": "string",
            "enum": ["red", "yellow", "blue", "green"],
            "description": "风险等级: red=高风险, yellow=中风险, blue=关注, green=正常",
        },
        "status": {
            "type": "string",
            "description": "订单状态，如 open, closed, overdue",
        },
        "date_start": {
            "type": "string",
            "description": "合同交期开始日期 YYYY-MM-DD",
        },
        "date_end": {
            "type": "string",
            "description": "合同交期结束日期 YYYY-MM-DD",
        },
        "owner": {
            "type": "string",
            "description": "订单负责人",
        },
        "overdue": {
            "type": "boolean",
            "description": "是否只查逾期订单（promised_date < 今天且未完成发货）",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限，默认20",
        },
    },
    "required": [],
}


@register_tool(
    name="search_orders",
    description="搜索销售订单。支持按关键词、客户、订单号、风险等级、状态、交期范围、负责人、是否逾期等条件查询。返回完整的订单信息。",
    parameters=PARAMETERS,
    display_name="销售订单查询",
)
async def search_orders(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    query = select(SaleOrder)
    count_query = select(func.count(SaleOrder.id))

    filters = []

    keyword = params.get("keyword")
    if keyword:
        like = f"%{keyword}%"
        kw_filter = (
            SaleOrder.order_no.ilike(like)
            | SaleOrder.customer.ilike(like)
            | SaleOrder.product_name.ilike(like)
        )
        filters.append(kw_filter)

    customer = params.get("customer")
    if customer:
        filters.append(SaleOrder.customer.ilike(f"%{customer}%"))

    order_no = params.get("order_no")
    if order_no:
        filters.append(SaleOrder.order_no.ilike(f"%{order_no}%"))

    risk_level = params.get("risk_level")
    if risk_level:
        filters.append(SaleOrder.risk_level == risk_level)

    status = params.get("status")
    if status:
        filters.append(SaleOrder.status == status)

    owner = params.get("owner")
    if owner:
        filters.append(SaleOrder.owner.ilike(f"%{owner}%"))

    date_start = params.get("date_start")
    if date_start:
        try:
            filters.append(SaleOrder.promised_date >= datetime.strptime(date_start, "%Y-%m-%d").date())
        except ValueError:
            pass

    date_end = params.get("date_end")
    if date_end:
        try:
            filters.append(SaleOrder.promised_date <= datetime.strptime(date_end, "%Y-%m-%d").date())
        except ValueError:
            pass

    overdue = params.get("overdue")
    if overdue:
        today = date.today()
        filters.append(SaleOrder.promised_date < today)
        filters.append(SaleOrder.delivery_completed_date.is_(None))

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    limit = params.get("limit")
    if limit:
        query = query.order_by(SaleOrder.promised_date.asc().nullslast()).limit(limit)
    else:
        query = query.order_by(SaleOrder.promised_date.asc().nullslast()).limit(20)
    result = await db.execute(query)
    orders = result.scalars().all()

    items = []
    for o in orders:
        item = create_search_result_item(
            instance=o,
            item_type="order",
            title=f"订单 {o.order_no}",
            subtitle=f"{o.customer or ''} | {o.product_name or ''}",
            url=f"/orders/{o.order_no}/lines/{o.line_no}",
            tags=[t for t in [o.risk_level, o.status] if t],
        )
        items.append(item)

    return {"total": total, "items": items}
