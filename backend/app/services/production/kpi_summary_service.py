"""372 驾驶舱 KPI 聚合服务 — 阶段 1a 最小版 + 阶段 2 冷冻分区

按 v2 规划 R4 渐进式上线：
- 1a 接通：today.{target_qty, completed_qty, completion_rate, in_progress_count}
           pending.{todo_count, missing_upph_count, unprocessed_change_count}
- 2 接通：frozen.{locked_count}（frozen_break_count 仍占位，等干预机制）
- 3 接通：material.{...}（待物料齐套接入）
- 4 接通：anomalies（待异常阈值全量）

口径（v2 规划 R1/R2）：
- 今日栏（区间相交）：start_date <= today AND end_date >= today
- 冷冻/配料栏（plan_date 归属）：plan_date BETWEEN ...
- 待排：plan_date 为空 或 plan_date > today+10
"""

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.production.schedule_plan import ProductionSchedulePlan


async def get_kpi_summary(db: AsyncSession) -> dict[str, Any]:
    today = date.today()

    # === 🔴 今日栏（区间相交口径，R2） ===
    today_stmt = select(
        func.coalesce(func.sum(ProductionSchedulePlan.source_order_qty), 0).label("target_qty"),
    ).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.start_date <= today,
        ProductionSchedulePlan.end_date >= today,
    )
    today_row = (await db.execute(today_stmt)).one()

    # 「已完成」当前没有专门的完成数量字段，先用 status='completed' 的 source_order_qty 求和占位
    completed_stmt = select(
        func.coalesce(func.sum(ProductionSchedulePlan.source_order_qty), 0).label("completed_qty"),
    ).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.status == "completed",
        ProductionSchedulePlan.start_date <= today,
        ProductionSchedulePlan.end_date >= today,
    )
    completed_row = (await db.execute(completed_stmt)).one()

    in_progress_stmt = select(func.count()).select_from(ProductionSchedulePlan).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.start_date <= today,
        ProductionSchedulePlan.end_date >= today,
    )
    in_progress_count = (await db.execute(in_progress_stmt)).scalar() or 0

    target_qty = float(today_row.target_qty or 0)
    completed_qty = float(completed_row.completed_qty or 0)
    completion_rate = (completed_qty / target_qty) if target_qty > 0 else None

    # === 📋 待排 / 变更（pending） ===
    # 待排：plan_date 为空
    todo_stmt = select(func.count()).select_from(ProductionSchedulePlan).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.plan_date.is_(None),
    )
    todo_count = (await db.execute(todo_stmt)).scalar() or 0

    # 缺 UPPH
    missing_upph_stmt = select(func.count()).select_from(ProductionSchedulePlan).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.upph.is_(None),
    )
    missing_upph_count = (await db.execute(missing_upph_stmt)).scalar() or 0

    # 未处理变更（needs_reschedule=True 的数量作为占位）
    unprocessed_change_stmt = select(func.count()).select_from(ProductionSchedulePlan).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.needs_reschedule.is_(True),
    )
    unprocessed_change_count = (await db.execute(unprocessed_change_stmt)).scalar() or 0

    # === 🟡 冷冻栏（plan_date 归属 1-3 天） ===
    # v2 阶段 2：locked_count 用真实查询；frozen_break_count 占位等干预机制
    frozen_start = today + timedelta(days=1)
    frozen_end = today + timedelta(days=3)
    frozen_locked_stmt = select(func.count()).select_from(ProductionSchedulePlan).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.plan_date.between(frozen_start, frozen_end),
    )
    frozen_locked_count = (await db.execute(frozen_locked_stmt)).scalar() or 0

    # === 🟢 配料栏（plan_date 归属 4-10 天） ===
    # v2 阶段 3：齐套数据暂用占位（kit_ready_rate=1.0 假设全部齐套），
    # 等 kit_analysis_service 完善后接入真实数据。
    # 待备料单数（配料区计划数）用真实查询。
    material_start = today + timedelta(days=4)
    material_end = today + timedelta(days=10)
    material_pending_stmt = select(func.count()).select_from(ProductionSchedulePlan).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.plan_date.between(material_start, material_end),
    )
    material_pending_count = (await db.execute(material_pending_stmt)).scalar() or 0

    return {
        "today": {
            "target_qty": target_qty,
            "completed_qty": completed_qty,
            "completion_rate": completion_rate,
            "in_progress_count": in_progress_count,
        },
        "frozen": {
            "locked_count": frozen_locked_count,
            "frozen_break_count": 0,
        },
        "material": {
            "kit_ready_rate": 1.0,  # 阶段 3 占位：假设全部齐套，等 kit_analysis 接入
            "shortage_count": 0,    # 阶段 3 占位
            "eta_delay_count": 0,   # 阶段 3 占位
            "pending_kit_count": material_pending_count,  # 真实：待备料单数（配料区计划数）
        },
        "pending": {
            "todo_count": todo_count,
            "missing_upph_count": missing_upph_count,
            "unprocessed_change_count": unprocessed_change_count,
        },
        # 阶段 1a 占位：schema 完整但内容为空
        "anomalies": [],
        "context_hints": {
            "production": ["today", "frozen", "material", "pending"],
            "materials": ["material", "pending"],
            "orders": ["today", "pending"],
        },
    }


async def get_today_cards(db: AsyncSession) -> list[dict[str, Any]]:
    """今日在产计划卡片（区间相交口径，R2）"""
    today = date.today()

    stmt = select(
        ProductionSchedulePlan.id,
        ProductionSchedulePlan.order_no,
        ProductionSchedulePlan.line_no,
        ProductionSchedulePlan.product_code,
        ProductionSchedulePlan.model_code,
        ProductionSchedulePlan.source_process_type,
        ProductionSchedulePlan.plan_date,
        ProductionSchedulePlan.start_date,
        ProductionSchedulePlan.end_date,
        ProductionSchedulePlan.source_order_qty,
        ProductionSchedulePlan.status,
        ProductionSchedulePlan.needs_reschedule,
    ).where(
        ProductionSchedulePlan.is_active.is_(True),
        ProductionSchedulePlan.start_date <= today,
        ProductionSchedulePlan.end_date >= today,
    ).order_by(ProductionSchedulePlan.order_no)

    rows = (await db.execute(stmt)).all()

    cards = []
    for r in rows:
        bucket = _resolve_bucket(r.source_process_type)
        cards.append({
            "id": str(r.id),
            "order_no": r.order_no or "-",
            "line_no": r.line_no,
            "product_code": r.product_code,
            "model_code": r.model_code,
            "bucket": bucket,
            "plan_date": r.plan_date.isoformat() if r.plan_date else None,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "target_qty": float(r.source_order_qty) if r.source_order_qty is not None else None,
            "status": r.status,
            "needs_reschedule": bool(r.needs_reschedule),
        })
    return cards


def _resolve_bucket(source_process_type: Optional[str]) -> str:
    """source_process_type → 驾驶舱 bucket（lean/assembly/packaging/mixed）"""
    if not source_process_type:
        return "mixed"
    pt = source_process_type.lower()
    if pt == "lean":
        return "lean"
    if pt == "assembly":
        return "assembly"
    if pt == "packaging":
        return "packaging"
    return "mixed"
