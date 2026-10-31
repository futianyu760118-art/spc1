"""手工改日期服务.

场景: 排产完成后, 计划员在「日期调整」页直接改某条计划的开工日.
规则: 以手工日期为准, 不级联推后其它计划; 产能超限只提示, 不拦截.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.production.capacity_slot import CapacitySlot
from app.models.production.schedule_plan import ProductionSchedulePlan
from app.services.production.capacity_slot_service import (
    MAX_DAILY_HOURS,
    recompute_plan_slots,
)
from app.services.production.config_service import ProductionScheduleConfigService


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


async def _resolve_bucket_capacity(
    db: AsyncSession,
    bucket: Optional[str],
    fallback_hours: Optional[float],
) -> tuple[float, bool]:
    """返回 (每日产能, 是否排周日), 与自动排产口径一致."""
    base = await ProductionScheduleConfigService(db).get_base_condition(bucket)
    daily_capacity = _to_float(base.get("daily_work_hours"), _to_float(fallback_hours, 8.5))
    daily_capacity = max(1.0, min(daily_capacity, MAX_DAILY_HOURS))
    return daily_capacity, bool(base.get("include_sunday"))


async def adjust_plan_date(
    db: AsyncSession,
    *,
    plan: ProductionSchedulePlan,
    target_date: date,
) -> dict[str, Any]:
    """把计划开工日改为 target_date 并重算产能槽.

    首个生产日强制占槽, 保证看板卡片落在用户选择的日期上.
    """
    bucket = str(plan.source_process_type or "").strip()
    quantity = _to_float(plan.quantity)
    upph = _to_float(plan.upph or plan.source_upph)
    manpower = int(plan.manpower or 0)
    if not bucket:
        raise ValueError("缺少排产段, 无法改期")
    if quantity <= 0 or upph <= 0:
        raise ValueError("缺少有效数量或UPPH, 无法改期")
    if manpower <= 0:
        manpower = 10

    total_hours = quantity / (upph * manpower)
    daily_capacity, include_sunday = await _resolve_bucket_capacity(
        db, bucket, plan.daily_work_hours
    )
    bookings = await recompute_plan_slots(
        db,
        plan_id=plan.id,
        department=str(plan.department or ""),
        schedule_bucket=bucket,
        order_no=plan.order_no,
        line_no=plan.line_no,
        total_hours=total_hours,
        target_start_date=target_date,
        daily_capacity=daily_capacity,
        include_sunday=include_sunday,
        serial_mode=False,
        target_end_date=None,
        earliest_fill_date=None,
        force_first_day=True,
    )
    if not bookings:
        raise ValueError("未能占用产能槽, 请检查数量/UPPH/人数")

    plan.plan_date = plan.start_date = min(b["date"] for b in bookings)
    plan.end_date = max(b["date"] for b in bookings)
    plan.needs_reschedule = False
    plan.reschedule_reason = None
    db.add(plan)

    return {
        "plan_id": plan.id,
        "order_no": plan.order_no,
        "line_no": plan.line_no,
        "target_date": target_date,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "total_hours": round(total_hours, 2),
        "success": True,
        "message": None,
    }


async def detect_capacity_conflicts(
    db: AsyncSession,
    *,
    plan_ids: list[int],
) -> list[dict[str, Any]]:
    """检测本次改期涉及的计划所在工段/日期是否超出日产能上限."""
    if not plan_ids:
        return []

    slot_rows = (
        await db.execute(
            select(CapacitySlot).where(
                CapacitySlot.plan_id.in_(plan_ids),
                CapacitySlot.is_active == True,
            )
        )
    ).scalars().all()
    if not slot_rows:
        return []

    pairs = {(slot.department, slot.schedule_bucket) for slot in slot_rows}
    start_date = min(_to_date(slot.slot_date) for slot in slot_rows)
    end_date = max(_to_date(slot.slot_date) for slot in slot_rows)
    base = await ProductionScheduleConfigService(db).get_base_conditions()
    limit_map = {
        item["schedule_bucket"]: max(1.0, min(float(item["daily_work_hours"] or 8), MAX_DAILY_HOURS))
        for item in base
    }

    conflicts: list[dict[str, Any]] = []
    for department, bucket in pairs:
        limit_hours = limit_map.get(bucket, 8.5)
        booked_rows = (
            await db.execute(
                select(
                    func.date(CapacitySlot.slot_date).label("slot_date"),
                    func.sum(CapacitySlot.hours).label("booked"),
                )
                .where(
                    CapacitySlot.department == department,
                    CapacitySlot.schedule_bucket == bucket,
                    CapacitySlot.is_active == True,
                    func.date(CapacitySlot.slot_date).between(start_date, end_date),
                )
                .group_by(func.date(CapacitySlot.slot_date))
            )
        ).all()
        for row in booked_rows:
            booked_hours = _to_float(row[1])
            if booked_hours <= limit_hours + 0.01:
                continue
            slot_date = row[0]
            if isinstance(slot_date, str):
                slot_date = date.fromisoformat(slot_date)
            else:
                slot_date = _to_date(slot_date)
            day_plan_ids = (
                await db.execute(
                    select(CapacitySlot.plan_id)
                    .where(
                        CapacitySlot.department == department,
                        CapacitySlot.schedule_bucket == bucket,
                        CapacitySlot.is_active == True,
                        func.date(CapacitySlot.slot_date) == slot_date,
                        CapacitySlot.plan_id.isnot(None),
                    )
                    .distinct()
                )
            ).scalars().all()
            conflicts.append({
                "date": slot_date,
                "department": department,
                "schedule_bucket": bucket,
                "booked_hours": round(booked_hours, 2),
                "limit_hours": round(limit_hours, 2),
                "plan_ids": [int(plan_id) for plan_id in day_plan_ids if plan_id is not None],
            })

    conflicts.sort(key=lambda item: (item["date"], item["department"], item["schedule_bucket"]))
    return conflicts
