"""Tool: 获取驾驶舱概览数据（今日交付 / 本周交付）"""

from typing import Any, Dict
from datetime import date, timedelta

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order.sale_order import SaleOrder
from app.models.material.material_demand import MaterialDemand
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "date_range": {
            "type": "string",
            "enum": ["today", "week", "month"],
            "description": "时间范围: today=今日, week=本周(未来7天), month=本月(未来30天)",
        },
    },
    "required": [],
}


@register_tool(
    name="get_dashboard_summary",
    description="获取供应链驾驶舱概览数据，包括应交订单数、风险分布、欠料统计等。支持查看今日、本周、本月的交付概况。",
    parameters=PARAMETERS,
    display_name="驾驶舱概览",
)
async def get_dashboard_summary(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    date_range = params.get("date_range", "today")
    today = date.today()

    if date_range == "week":
        end_date = today + timedelta(days=7)
        label = "本周(未来7天)"
    elif date_range == "month":
        end_date = today + timedelta(days=30)
        label = "本月(未来30天)"
    else:
        end_date = today
        label = "今日"

    # 应交订单统计
    base_filter = [
        SaleOrder.promised_date >= today,
        SaleOrder.promised_date <= end_date,
        SaleOrder.delivery_completed_date.is_(None),
    ]
    if date_range == "today":
        base_filter = [
            SaleOrder.promised_date == today,
        ]

    stats_query = select(
        func.count(SaleOrder.id).label("total"),
        func.sum(case((SaleOrder.risk_level == "red", 1), else_=0)).label("red_count"),
        func.sum(case((SaleOrder.risk_level == "yellow", 1), else_=0)).label("yellow_count"),
        func.sum(case((SaleOrder.risk_level == "blue", 1), else_=0)).label("blue_count"),
        func.sum(case((SaleOrder.risk_level == "green", 1), else_=0)).label("green_count"),
    ).where(*base_filter)
    stats_result = await db.execute(stats_query)
    stats = stats_result.first()

    # 逾期订单
    overdue_count_result = await db.execute(
        select(func.count(SaleOrder.id)).where(
            SaleOrder.promised_date < today,
            SaleOrder.delivery_completed_date.is_(None),
        )
    )
    overdue_count = overdue_count_result.scalar() or 0

    # 欠料统计
    shortage_result = await db.execute(
        select(func.count(MaterialDemand.id.distinct())).where(MaterialDemand.shortage_flag == True)
    )
    shortage_count = shortage_result.scalar() or 0

    # 应交订单列表（前10条）
    order_query = (
        select(SaleOrder)
        .where(*base_filter)
        .order_by(SaleOrder.risk_score.desc().nullslast())
        .limit(10)
    )
    order_result = await db.execute(order_query)
    orders = order_result.scalars().all()

    order_items = []
    for o in orders:
        order_items.append({
            "type": "order",
            "title": f"订单 {o.order_no}",
            "subtitle": f"{o.customer or ''} | {o.product_name or ''}",
            "url": f"/orders/{o.order_no}/lines/{o.line_no}",
            "tags": [t for t in [o.risk_level, o.status] if t],
            "order_no": o.order_no,
            "line_no": o.line_no,
            "customer": o.customer,
            "product_name": o.product_name,
            "order_qty": float(o.order_qty) if o.order_qty else None,
            "completed_qty": float(o.completed_qty) if o.completed_qty else None,
            "promised_date": str(o.promised_date) if o.promised_date else None,
            "risk_level": o.risk_level,
            "risk_score": float(o.risk_score) if o.risk_score else None,
            "status": o.status,
            "owner": o.owner,
            "customer_grade": o.customer_grade,
            "shipping_plan": str(o.shipping_plan) if o.shipping_plan else None,
            "material_ready_date": str(o.material_ready_date) if o.material_ready_date else None,
        })

    return {
        "label": label,
        "summary": {
            "due_total": stats.total or 0,
            "red_count": stats.red_count or 0,
            "yellow_count": stats.yellow_count or 0,
            "blue_count": stats.blue_count or 0,
            "green_count": stats.green_count or 0,
            "overdue_count": overdue_count,
            "shortage_count": shortage_count,
        },
        "total": stats.total or 0,
        "items": order_items,
    }
