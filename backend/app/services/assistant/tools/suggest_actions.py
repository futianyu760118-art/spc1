"""Tool: 行动建议 — 基于当前数据状态生成可执行的行动建议"""

from typing import Any, Dict
from datetime import date, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order.sale_order import SaleOrder
from app.models.material.purchase_order import PurchaseOrder
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "context": {
            "type": "string",
            "enum": ["daily_briefing", "order_followup", "procurement_alert", "weekly_summary"],
            "description": "建议场景: daily_briefing=每日简报, order_followup=订单跟进, procurement_alert=采购预警, weekly_summary=周总结",
        },
        "order_no": {
            "type": "string",
            "description": "针对特定订单生成建议（可选）",
        },
    },
    "required": ["context"],
}


@register_tool(
    name="suggest_actions",
    description="基于当前数据状态生成可执行的行动建议。支持每日简报、订单跟进建议、采购预警、周总结等场景。返回结构化的行动建议列表。",
    parameters=PARAMETERS,
    display_name="行动建议",
    keywords=["建议", "行动", "简报", "预警", "跟进", "该做什么", "待办", "提醒"],
    category="decision",
)
async def suggest_actions(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    context = params.get("context", "daily_briefing")
    order_no = params.get("order_no")
    today = date.today()

    actions: list = []

    if context == "daily_briefing":
        actions = await _daily_briefing(db, today)
    elif context == "order_followup":
        actions = await _order_followup(db, today, order_no)
    elif context == "procurement_alert":
        actions = await _procurement_alert(db, today)
    elif context == "weekly_summary":
        actions = await _weekly_summary(db, today)

    return {
        "context": context,
        "date": str(today),
        "actions": actions,
        "total": len(actions),
    }


async def _daily_briefing(db: AsyncSession, today: date) -> list:
    """每日简报：今日应交、逾期、高风险订单统计 + 行动建议"""
    actions = []

    # 今日应交
    due_today = await db.execute(
        select(func.count(SaleOrder.id)).where(
            SaleOrder.promised_date == today,
            SaleOrder.delivery_completed_date.is_(None),
        )
    )
    due_count = due_today.scalar() or 0

    # 逾期未交
    overdue = await db.execute(
        select(func.count(SaleOrder.id)).where(
            SaleOrder.promised_date < today,
            SaleOrder.delivery_completed_date.is_(None),
        )
    )
    overdue_count = overdue.scalar() or 0

    # 高风险订单
    high_risk = await db.execute(
        select(func.count(SaleOrder.id)).where(
            SaleOrder.risk_level == "red",
            SaleOrder.delivery_completed_date.is_(None),
        )
    )
    high_risk_count = high_risk.scalar() or 0

    # 本周应交
    week_end = today + timedelta(days=(6 - today.weekday()))
    week_due = await db.execute(
        select(func.count(SaleOrder.id)).where(
            SaleOrder.promised_date >= today,
            SaleOrder.promised_date <= week_end,
            SaleOrder.delivery_completed_date.is_(None),
        )
    )
    week_due_count = week_due.scalar() or 0

    if due_count > 0:
        actions.append({
            "priority": "high",
            "category": "delivery",
            "title": f"今日有 {due_count} 个订单应交付",
            "description": "请确认生产进度和物料齐套情况，确保按时交付。",
            "action_type": "query",
            "action_params": {"tool": "search_orders", "params": {"date_start": str(today), "date_end": str(today)}},
        })

    if overdue_count > 0:
        actions.append({
            "priority": "critical",
            "category": "overdue",
            "title": f"当前有 {overdue_count} 个订单逾期未交",
            "description": "逾期订单需要立即跟进，确认延期原因并制定补救计划。",
            "action_type": "query",
            "action_params": {"tool": "search_orders", "params": {"overdue": True}},
        })

    if high_risk_count > 0:
        actions.append({
            "priority": "high",
            "category": "risk",
            "title": f"有 {high_risk_count} 个高风险订单需关注",
            "description": "高风险订单可能面临交期延误，建议提前协调资源。",
            "action_type": "query",
            "action_params": {"tool": "search_orders", "params": {"risk_level": "red"}},
        })

    if week_due_count > 0:
        actions.append({
            "priority": "medium",
            "category": "planning",
            "title": f"本周还有 {week_due_count} 个订单待交付",
            "description": "建议提前确认本周交付计划的可行性。",
            "action_type": "query",
            "action_params": {"tool": "search_orders", "params": {"date_start": str(today), "date_end": str(week_end)}},
        })

    if not actions:
        actions.append({
            "priority": "low",
            "category": "info",
            "title": "今日暂无紧急事项",
            "description": "当前没有逾期或高风险订单，可以关注中长期计划。",
            "action_type": "none",
            "action_params": {},
        })

    return actions


async def _order_followup(db: AsyncSession, today: date, order_no: str = None) -> list:
    """订单跟进建议"""
    actions = []

    if order_no:
        # 针对特定订单的跟进建议
        result = await db.execute(
            select(SaleOrder).where(SaleOrder.order_no.ilike(f"%{order_no}%")).limit(1)
        )
        order = result.scalar_one_or_none()
        if order:
            if order.delivery_completed_date:
                actions.append({
                    "priority": "low",
                    "category": "info",
                    "title": f"订单 {order.order_no} 已完成交付",
                    "description": f"交付完成日期: {order.delivery_completed_date}",
                    "action_type": "none",
                    "action_params": {},
                })
            else:
                if order.risk_level == "red":
                    actions.append({
                        "priority": "critical",
                        "category": "risk",
                        "title": f"订单 {order.order_no} 为高风险状态",
                        "description": "建议立即确认物料齐套和生产进度，协调资源优先处理。",
                        "action_type": "query",
                        "action_params": {"tool": "search_purchase_orders", "params": {"order_no": order.order_no}},
                    })
                if order.promised_date and order.promised_date < today:
                    days_overdue = (today - order.promised_date).days
                    actions.append({
                        "priority": "critical",
                        "category": "overdue",
                        "title": f"订单 {order.order_no} 已逾期 {days_overdue} 天",
                        "description": "建议联系客户沟通新交期，同时加速生产进度。",
                        "action_type": "query",
                        "action_params": {"tool": "search_production", "params": {"order_no": order.order_no}},
                    })
                elif order.promised_date:
                    days_left = (order.promised_date - today).days
                    if days_left <= 3:
                        actions.append({
                            "priority": "high",
                            "category": "delivery",
                            "title": f"订单 {order.order_no} 距交期仅剩 {days_left} 天",
                            "description": "建议确认最终生产和发货准备情况。",
                            "action_type": "query",
                            "action_params": {"tool": "search_production", "params": {"order_no": order.order_no}},
                        })

                # 检查采购情况
                po_count = await db.execute(
                    select(func.count(PurchaseOrder.id)).where(
                        PurchaseOrder.order_no.ilike(f"%{order.order_no}%")
                    )
                )
                po_total = po_count.scalar() or 0
                if po_total > 0:
                    actions.append({
                        "priority": "medium",
                        "category": "procurement",
                        "title": f"订单 {order.order_no} 关联 {po_total} 个采购订单",
                        "description": "建议检查采购到货情况，确保物料按时到位。",
                        "action_type": "query",
                        "action_params": {"tool": "search_purchase_orders", "params": {"order_no": order.order_no}},
                    })
        else:
            actions.append({
                "priority": "low",
                "category": "info",
                "title": f"未找到订单 {order_no}",
                "description": "请确认订单号是否正确。",
                "action_type": "none",
                "action_params": {},
            })
    else:
        # 通用跟进建议：关注即将到期的订单
        upcoming = await db.execute(
            select(func.count(SaleOrder.id)).where(
                SaleOrder.promised_date >= today,
                SaleOrder.promised_date <= today + timedelta(days=3),
                SaleOrder.delivery_completed_date.is_(None),
            )
        )
        upcoming_count = upcoming.scalar() or 0
        if upcoming_count > 0:
            actions.append({
                "priority": "high",
                "category": "delivery",
                "title": f"未来3天有 {upcoming_count} 个订单即将到期",
                "description": "建议逐一确认交付准备情况。",
                "action_type": "query",
                "action_params": {"tool": "search_orders", "params": {"date_start": str(today), "date_end": str(today + timedelta(days=3))}},
            })

    return actions


async def _procurement_alert(db: AsyncSession, today: date) -> list:
    """采购预警"""
    actions = []

    # 查找关联高风险订单的采购单
    high_risk_orders = await db.execute(
        select(SaleOrder.order_no).where(
            SaleOrder.risk_level == "red",
            SaleOrder.delivery_completed_date.is_(None),
        ).limit(10)
    )
    risk_order_nos = [r[0] for r in high_risk_orders.fetchall()]

    if risk_order_nos:
        actions.append({
            "priority": "critical",
            "category": "procurement",
            "title": f"有 {len(risk_order_nos)} 个高风险订单的采购需要关注",
            "description": "这些订单的物料供应可能存在风险，建议检查采购到货进度。",
            "action_type": "query",
            "action_params": {"tool": "search_purchase_orders", "params": {"order_no": risk_order_nos[0]}},
        })

    # 检查逾期订单的采购情况
    overdue_orders = await db.execute(
        select(SaleOrder.order_no).where(
            SaleOrder.promised_date < today,
            SaleOrder.delivery_completed_date.is_(None),
        ).limit(5)
    )
    overdue_nos = [r[0] for r in overdue_orders.fetchall()]

    if overdue_nos:
        actions.append({
            "priority": "high",
            "category": "procurement",
            "title": f"逾期订单的采购跟进",
            "description": f"有 {len(overdue_nos)} 个逾期订单，建议确认其采购物料是否已到位。",
            "action_type": "query",
            "action_params": {"tool": "search_purchase_orders", "params": {"order_no": overdue_nos[0]}},
        })

    if not actions:
        actions.append({
            "priority": "low",
            "category": "info",
            "title": "采购状况正常",
            "description": "当前没有需要紧急关注的采购预警。",
            "action_type": "none",
            "action_params": {},
        })

    return actions


async def _weekly_summary(db: AsyncSession, today: date) -> list:
    """周总结建议"""
    actions = []
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # 本周已交付
    delivered = await db.execute(
        select(func.count(SaleOrder.id)).where(
            SaleOrder.delivery_completed_date >= week_start,
            SaleOrder.delivery_completed_date <= today,
        )
    )
    delivered_count = delivered.scalar() or 0

    # 本周应交但未交
    missed = await db.execute(
        select(func.count(SaleOrder.id)).where(
            SaleOrder.promised_date >= week_start,
            SaleOrder.promised_date <= today,
            SaleOrder.delivery_completed_date.is_(None),
        )
    )
    missed_count = missed.scalar() or 0

    # 下周应交
    next_week_start = week_end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)
    next_week = await db.execute(
        select(func.count(SaleOrder.id)).where(
            SaleOrder.promised_date >= next_week_start,
            SaleOrder.promised_date <= next_week_end,
            SaleOrder.delivery_completed_date.is_(None),
        )
    )
    next_week_count = next_week.scalar() or 0

    actions.append({
        "priority": "medium",
        "category": "summary",
        "title": f"本周交付情况：已交 {delivered_count} 单，未交 {missed_count} 单",
        "description": f"本周交付完成率: {round(delivered_count / max(delivered_count + missed_count, 1) * 100)}%",
        "action_type": "none",
        "action_params": {},
    })

    if missed_count > 0:
        actions.append({
            "priority": "high",
            "category": "overdue",
            "title": f"本周有 {missed_count} 个订单未按时交付",
            "description": "建议分析延误原因，制定改善措施。",
            "action_type": "query",
            "action_params": {"tool": "search_orders", "params": {"date_start": str(week_start), "date_end": str(today), "overdue": True}},
        })

    if next_week_count > 0:
        actions.append({
            "priority": "medium",
            "category": "planning",
            "title": f"下周有 {next_week_count} 个订单待交付",
            "description": "建议提前做好下周交付计划和资源协调。",
            "action_type": "query",
            "action_params": {"tool": "search_orders", "params": {"date_start": str(next_week_start), "date_end": str(next_week_end)}},
        })

    return actions
