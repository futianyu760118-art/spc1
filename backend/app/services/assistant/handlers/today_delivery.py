"""今日交付盘点 handler"""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.assistant.schemas import AssistantReply, AssistantCard
from app.services.assistant.intent_router import register_handler
from app.services.dashboard.dashboard_service import DashboardService


@register_handler("today_delivery")
async def handle_today_delivery(db: AsyncSession, params: Dict[str, Any]) -> AssistantReply:
    """今日交付盘点：汇总 + 订单列表"""
    svc = DashboardService(db)

    overview = await svc.get_today_overview()
    due_orders_result = await svc.get_today_due_orders(page=1, page_size=20)

    # 构造摘要文本
    due_count = overview.due_today
    red_count = overview.due_today_red
    yellow_count = overview.due_today_yellow
    normal_count = due_count - red_count - yellow_count

    text = f"今日共 {due_count} 笔订单应交付"
    if red_count > 0 or yellow_count > 0:
        parts = []
        if red_count > 0:
            parts.append(f"{red_count} 笔高风险")
        if yellow_count > 0:
            parts.append(f"{yellow_count} 笔中风险")
        text += f"，其中{'、'.join(parts)}"
    text += "。"

    if due_count == 0:
        text = "今日无应交订单，一切正常！"

    # 汇总卡片
    summary_card = AssistantCard(
        type="summary",
        title="今日交付概览",
        payload={
            "items": [
                {"label": "应交总数", "value": due_count, "color": "#1890ff"},
                {"label": "高风险", "value": red_count, "color": "#f5222d"},
                {"label": "中风险", "value": yellow_count, "color": "#faad14"},
                {"label": "正常", "value": normal_count, "color": "#52c41a"},
            ]
        },
    )

    # 订单列表卡片
    orders = due_orders_result.items if hasattr(due_orders_result, 'items') else []
    order_list = []
    for o in orders[:20]:
        order_list.append({
            "order_no": o.order_no,
            "customer": o.customer,
            "product_name": o.product_name,
            "promised_date": str(o.promised_date) if o.promised_date else "",
            "risk_level": o.risk_level,
            "owner": o.owner,
        })

    order_card = AssistantCard(
        type="order_list",
        title=f"今日应交订单（前 {len(order_list)} 笔）",
        payload={
            "orders": order_list,
            "total": due_orders_result.total if hasattr(due_orders_result, 'total') else len(order_list),
        },
    )

    cards = [summary_card]
    if order_list:
        cards.append(order_card)

    suggestions = []
    if red_count > 0:
        suggestions.append("查看高风险订单")
    if due_count > 20:
        suggestions.append("查看更多订单")

    return AssistantReply(
        intent="today_delivery",
        text=text,
        cards=cards,
        suggestions=suggestions,
    )
