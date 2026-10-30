"""插单服务（订单池新单 / 同订单返单）.

插入日期优先, 同部门同排产段已排计划整体顺延.
返回新计划 + 被顺延清单 + 产能冲突, 由调用方落库/提示.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.production.schedule_plan import ProductionSchedulePlan
from app.services.production.capacity_slot_service import (
    recompute_plan_slots,
    release_slots_for_plan,
)
from app.services.production.frozen_zone_service import is_plan_in_frozen_zone
from app.services.production.manual_date_adjust_service import (
    _resolve_bucket_capacity,
    _to_float,
    detect_capacity_conflicts,
)

logger = logging.getLogger(__name__)

INSERTABLE_BUCKETS = {"lean", "assembly", "packaging"}
MAX_RESERVE_DAYS = 365


def _is_production_day(day: date, include_sunday: bool) -> bool:
    return include_sunday or day.weekday() != 6


def _reserve_window(
    target_date: date,
    total_hours: float,
    daily_capacity: float,
    include_sunday: bool,
) -> list[date]:
    """按每天满产能从 target_date 起预留生产日, 用于确定顺延窗口."""
    remaining = float(total_hours)
    cur = target_date
    days: list[date] = []
    while remaining > 0.01 and len(days) < MAX_RESERVE_DAYS:
        if not _is_production_day(cur, include_sunday):
            cur += timedelta(days=1)
            continue
        days.append(cur)
        remaining -= min(daily_capacity, remaining)
        cur += timedelta(days=1)
    return days


def _plan_duration(plan: ProductionSchedulePlan) -> int:
    if not plan.start_date or not plan.end_date:
        return 1
    return max((plan.end_date - plan.start_date).days + 1, 1)


async def _collect_push_moves(
    db: AsyncSession,
    *,
    department: str,
    bucket: str,
    reserved_start: date,
    reserved_end: date,
) -> list[dict[str, Any]]:
    """收集插入点之后同段计划的顺延位置（只算不写）."""
    rows = (
        await db.execute(
            select(ProductionSchedulePlan)
            .where(
                ProductionSchedulePlan.is_active == True,
                ProductionSchedulePlan.department == department,
                ProductionSchedulePlan.source_process_type == bucket,
                ProductionSchedulePlan.start_date.isnot(None),
                ProductionSchedulePlan.end_date.isnot(None),
                ProductionSchedulePlan.end_date >= reserved_start,
            )
            .order_by(
                ProductionSchedulePlan.start_date.asc(),
                ProductionSchedulePlan.id.asc(),
            )
        )
    ).scalars().all()

    shift_days = (reserved_end - reserved_start).days + 1
    moves: list[dict[str, Any]] = []
    for plan in rows:
        if _to_float(plan.quantity) <= 0 or _to_float(plan.upph) <= 0:
            continue
        duration = _plan_duration(plan)
        new_start = plan.start_date + timedelta(days=shift_days)
        if plan.start_date < reserved_start:
            new_start = max(new_start, reserved_end + timedelta(days=1))
        moves.append({
            "plan": plan,
            "old_start": plan.start_date,
            "old_end": plan.end_date,
            "new_start": new_start,
            "new_end": new_start + timedelta(days=duration - 1),
        })
    return moves


async def _collect_push_moves_for_shift(
    db: AsyncSession,
    *,
    department: str,
    bucket: str,
    threshold_start: date,
    shift_days: int,
) -> list[dict[str, Any]]:
    """按固定天数整体顺延 threshold_start 之后的同段计划（拆单用，只顺延一次）."""
    if shift_days <= 0:
        return []

    rows = (
        await db.execute(
            select(ProductionSchedulePlan)
            .where(
                ProductionSchedulePlan.is_active == True,
                ProductionSchedulePlan.department == department,
                ProductionSchedulePlan.source_process_type == bucket,
                ProductionSchedulePlan.start_date.isnot(None),
                ProductionSchedulePlan.end_date.isnot(None),
                ProductionSchedulePlan.end_date >= threshold_start,
            )
            .order_by(
                ProductionSchedulePlan.start_date.asc(),
                ProductionSchedulePlan.id.asc(),
            )
        )
    ).scalars().all()

    moves: list[dict[str, Any]] = []
    for plan in rows:
        if _to_float(plan.quantity) <= 0 or _to_float(plan.upph) <= 0:
            continue
        duration = _plan_duration(plan)
        new_start = plan.start_date + timedelta(days=shift_days)
        moves.append({
            "plan": plan,
            "old_start": plan.start_date,
            "old_end": plan.end_date,
            "new_start": new_start,
            "new_end": new_start + timedelta(days=duration - 1),
        })
    return moves


async def _apply_push_moves(
    db: AsyncSession,
    moves: list[dict[str, Any]],
    *,
    operator: str,
    reason: str,
    daily_capacity: float,
    include_sunday: bool,
) -> list[dict[str, Any]]:
    """落库顺延: 旧版本失效释放槽 → 新版本占槽."""
    if not moves:
        return []

    for move in moves:
        old_plan = move["plan"]
        old_plan.is_active = False
        old_plan.reschedule_reason = reason
        db.add(old_plan)
        await release_slots_for_plan(db, old_plan.id)
    await db.flush()

    pushed: list[dict[str, Any]] = []
    for move in moves:
        old_plan = move["plan"]
        new_plan = ProductionSchedulePlan(
            department=old_plan.department,
            plan_date=move["new_start"],
            order_no=old_plan.order_no,
            line_no=old_plan.line_no,
            product_code=old_plan.product_code,
            model_code=old_plan.model_code,
            quantity=old_plan.quantity,
            planned_qty=old_plan.planned_qty,
            owner=old_plan.owner,
            start_date=move["new_start"],
            end_date=move["new_end"],
            priority=old_plan.priority,
            status=old_plan.status,
            upph=old_plan.upph,
            manpower=old_plan.manpower,
            daily_work_hours=old_plan.daily_work_hours,
            plan_version=int(old_plan.plan_version or 1) + 1,
            is_active=True,
            source_promised_date=old_plan.source_promised_date,
            source_order_qty=old_plan.source_order_qty,
            source_product_code=old_plan.source_product_code,
            source_product_model=old_plan.source_product_model,
            source_upph=old_plan.source_upph,
            source_process_type=old_plan.source_process_type,
            needs_reschedule=False,
            reschedule_reason=None,
            previous_plan_id=old_plan.id,
            sync_batch_no=old_plan.sync_batch_no,
            remark=reason,
            created_by=operator,
        )
        db.add(new_plan)
        await db.flush()

        pushed_qty = _to_float(new_plan.quantity)
        pushed_upph = _to_float(new_plan.upph)
        pushed_manpower = max(int(new_plan.manpower or 10), 1)
        pushed_hours = (
            pushed_qty / (pushed_upph * pushed_manpower) if pushed_upph > 0 else 0
        )
        bookings = await recompute_plan_slots(
            db,
            plan_id=new_plan.id,
            department=str(new_plan.department or ""),
            schedule_bucket=str(new_plan.source_process_type or ""),
            order_no=new_plan.order_no,
            line_no=new_plan.line_no,
            total_hours=pushed_hours,
            target_start_date=move["new_start"],
            daily_capacity=daily_capacity,
            include_sunday=include_sunday,
            serial_mode=False,
            target_end_date=None,
            earliest_fill_date=None,
        )
        if bookings:
            new_plan.plan_date = new_plan.start_date = min(b["date"] for b in bookings)
            new_plan.end_date = max(b["date"] for b in bookings)
            db.add(new_plan)

        pushed.append({
            "plan_id": old_plan.id,
            "new_plan_id": new_plan.id,
            "order_no": new_plan.order_no,
            "line_no": new_plan.line_no,
            "old_start": move["old_start"],
            "old_end": move["old_end"],
            "new_start": new_plan.start_date,
            "new_end": new_plan.end_date,
        })

    return pushed


async def insert_schedule_plan(
    db: AsyncSession,
    *,
    order_no: str,
    line_no: str,
    department: str,
    schedule_bucket: str,
    target_date: date,
    quantity: float,
    upph: Optional[float],
    manpower: int,
    daily_work_hours: Optional[float] = None,
    total_hours_override: Optional[float] = None,
    product_code: Optional[str] = None,
    model_code: Optional[str] = None,
    owner: Optional[str] = None,
    priority: str = "normal",
    source_promised_date: Optional[date] = None,
    allow_duplicate: bool = False,
    source_order_qty: Optional[float] = None,
    push_conflicts: bool = True,
    remark: Optional[str] = None,
    break_frozen_reason: Optional[str] = None,
    operator: str,
) -> tuple[ProductionSchedulePlan, list[dict[str, Any]], list[dict[str, Any]]]:
    if schedule_bucket not in INSERTABLE_BUCKETS:
        raise ValueError("排产段只支持 lean/assembly/packaging")
    if quantity <= 0 or int(manpower or 0) <= 0:
        raise ValueError("数量、人数必须大于 0")
    manpower = max(int(manpower), 1)

    if total_hours_override is not None:
        total_hours = float(total_hours_override)
        if total_hours <= 0:
            raise ValueError("返工工时为 0，无法排产")
        if not upph or upph <= 0:
            upph = quantity / (total_hours * manpower)
    else:
        if not upph or upph <= 0:
            raise ValueError("UPPH 必须大于 0")
        total_hours = quantity / (float(upph) * manpower)

    if not allow_duplicate:
        existing = (
            await db.execute(
                select(ProductionSchedulePlan.id).where(
                    ProductionSchedulePlan.order_no == order_no,
                    ProductionSchedulePlan.line_no == line_no,
                    ProductionSchedulePlan.source_process_type == schedule_bucket,
                    ProductionSchedulePlan.is_active == True,
                )
            )
        ).scalars().first()
        if existing:
            raise ValueError("该订单行在此排产段已排产；返单/返工请勾选「允许同订单重复」")

    if source_order_qty is None:
        existing_source_qty = (
            await db.execute(
                select(func.max(ProductionSchedulePlan.source_order_qty)).where(
                    ProductionSchedulePlan.order_no == order_no,
                    ProductionSchedulePlan.line_no == line_no,
                    ProductionSchedulePlan.source_process_type == schedule_bucket,
                    ProductionSchedulePlan.is_active == True,
                )
            )
        ).scalar()
        if existing_source_qty is not None and _to_float(existing_source_qty) > quantity:
            source_order_qty = _to_float(existing_source_qty)

    daily_capacity, include_sunday = await _resolve_bucket_capacity(
        db, schedule_bucket, daily_work_hours
    )
    window = _reserve_window(target_date, total_hours, daily_capacity, include_sunday)
    if not window:
        raise ValueError("无法计算插入计划的占用日期")
    reserved_start, reserved_end = window[0], window[-1]

    if is_plan_in_frozen_zone(reserved_start) and not (break_frozen_reason or "").strip():
        raise ValueError("插入日期在冷冻区（1-3 天内开工），必须填写破冻理由")

    moves = await _collect_push_moves(
        db,
        department=department,
        bucket=schedule_bucket,
        reserved_start=reserved_start,
        reserved_end=reserved_end,
    ) if push_conflicts else []
    frozen_push = [
        move for move in moves if is_plan_in_frozen_zone(move["new_start"])
    ]
    if frozen_push and not (break_frozen_reason or "").strip():
        raise ValueError(
            f"顺延会把 {len(frozen_push)} 条计划推入冷冻区，必须填写破冻理由"
        )

    push_reason = f"被返单/插单 {order_no}/{line_no} 插入 {reserved_start} 顺延 {len(window)} 天"
    pushed = await _apply_push_moves(
        db,
        moves,
        operator=operator,
        reason=push_reason,
        daily_capacity=daily_capacity,
        include_sunday=include_sunday,
    )

    plan = ProductionSchedulePlan(
        department=department,
        plan_date=reserved_start,
        order_no=order_no,
        line_no=line_no,
        product_code=product_code,
        model_code=model_code,
        quantity=quantity,
        planned_qty=quantity,
        owner=owner,
        start_date=reserved_start,
        end_date=reserved_end,
        priority=priority or "normal",
        status="planned",
        upph=upph,
        manpower=int(manpower),
        daily_work_hours=daily_work_hours or daily_capacity,
        plan_version=1,
        is_active=True,
        source_promised_date=source_promised_date,
        source_order_qty=source_order_qty if source_order_qty is not None else quantity,
        source_product_code=product_code,
        source_product_model=model_code,
        source_upph=upph,
        source_process_type=schedule_bucket,
        previous_plan_id=None,
        remark=remark or "手工插入",
        created_by=operator,
    )
    db.add(plan)
    await db.flush()

    bookings = await recompute_plan_slots(
        db,
        plan_id=plan.id,
        department=department,
        schedule_bucket=schedule_bucket,
        order_no=order_no,
        line_no=line_no,
        total_hours=total_hours,
        target_start_date=reserved_start,
        daily_capacity=daily_capacity,
        include_sunday=include_sunday,
        serial_mode=False,
        target_end_date=None,
        earliest_fill_date=None,
        force_first_day=True,
    )
    if bookings:
        plan.plan_date = plan.start_date = min(b["date"] for b in bookings)
        plan.end_date = max(b["date"] for b in bookings)
        db.add(plan)

    conflicts = await detect_capacity_conflicts(db, plan_ids=[plan.id])
    return plan, pushed, conflicts


async def split_schedule_plan(
    db: AsyncSession,
    *,
    plan_id: int,
    batches: list[dict[str, Any]],
    push_conflicts: bool = True,
    break_frozen_reason: Optional[str] = None,
    operator: str,
) -> tuple[list[ProductionSchedulePlan], list[dict[str, Any]], float, list[dict[str, Any]]]:
    """把一个计划按数量拆成多批, 每批独立日期/占槽.

    batches: [{"quantity": float, "target_date": date}, ...]
    返回 (新批次计划, 被顺延计划, 未拆数量, 产能冲突)
    """
    original = (
        await db.execute(
            select(ProductionSchedulePlan).where(ProductionSchedulePlan.id == plan_id)
        )
    ).scalar_one_or_none()
    if not original or not original.is_active:
        raise ValueError("计划不存在或已失效")

    bucket = str(original.source_process_type or "").strip()
    if bucket not in INSERTABLE_BUCKETS:
        raise ValueError("该排产段不支持拆单")
    if not batches:
        raise ValueError("至少需要一个批次")

    sorted_batches = sorted(batches, key=lambda item: item["target_date"])
    for item in sorted_batches:
        if float(item.get("quantity") or 0) <= 0:
            raise ValueError("批次数量必须大于 0")

    original_qty = _to_float(original.quantity)
    total_qty = sum(float(item["quantity"]) for item in sorted_batches)
    if total_qty > original_qty + 0.01:
        raise ValueError(f"拆分数量 {total_qty} 超过计划数量 {original_qty}")

    upph = _to_float(original.upph) or _to_float(original.source_upph)
    if upph <= 0:
        raise ValueError("计划缺少有效 UPPH, 无法拆单")
    manpower = max(int(original.manpower or 10), 1)

    daily_capacity, include_sunday = await _resolve_bucket_capacity(
        db, bucket, original.daily_work_hours
    )

    windows: list[list[date]] = []
    previous_end: Optional[date] = None
    for item in sorted_batches:
        hours = float(item["quantity"]) / (upph * manpower)
        window = _reserve_window(
            item["target_date"], hours, daily_capacity, include_sunday
        )
        if not window:
            raise ValueError("无法计算批次占用日期")
        if previous_end and window[0] <= previous_end:
            raise ValueError("批次日期互相重叠, 请调整开始日期")
        windows.append(window)
        previous_end = window[-1]

    extra_days = max(0, sum(len(window) for window in windows) - _plan_duration(original))
    threshold_start = windows[0][0]

    original.is_active = False
    original.reschedule_reason = f"拆单：拆为 {len(sorted_batches)} 批"
    db.add(original)
    await release_slots_for_plan(db, original.id)
    await db.flush()

    moves = (
        await _collect_push_moves_for_shift(
            db,
            department=str(original.department or ""),
            bucket=bucket,
            threshold_start=threshold_start,
            shift_days=extra_days,
        )
        if push_conflicts
        else []
    )
    frozen_push = [move for move in moves if is_plan_in_frozen_zone(move["new_start"])]
    if frozen_push and not (break_frozen_reason or "").strip():
        raise ValueError(f"顺延会把 {len(frozen_push)} 条计划推入冷冻区，必须填写破冻理由")

    pushed = await _apply_push_moves(
        db,
        moves,
        operator=operator,
        reason=(
            f"被 {original.order_no}/{original.line_no} 拆单"
            f"（{total_qty:g}/{original_qty:g}）顺延 {extra_days} 天"
        ),
        daily_capacity=daily_capacity,
        include_sunday=include_sunday,
    )

    source_total = _to_float(original.source_order_qty) or original_qty
    new_plans: list[ProductionSchedulePlan] = []
    for index, (item, window) in enumerate(zip(sorted_batches, windows), start=1):
        batch_remark = f"拆单批次 {index}/{len(sorted_batches)}"
        plan, _, _ = await insert_schedule_plan(
            db,
            order_no=str(original.order_no or ""),
            line_no=str(original.line_no or "1"),
            department=str(original.department or ""),
            schedule_bucket=bucket,
            target_date=item["target_date"],
            quantity=float(item["quantity"]),
            upph=upph,
            manpower=manpower,
            daily_work_hours=_to_float(original.daily_work_hours) or None,
            product_code=original.product_code,
            model_code=original.model_code,
            owner=original.owner,
            priority=str(original.priority or "normal"),
            source_promised_date=original.source_promised_date,
            allow_duplicate=True,
            source_order_qty=source_total,
            push_conflicts=False,
            remark=batch_remark,
            break_frozen_reason=break_frozen_reason,
            operator=operator,
        )
        new_plans.append(plan)

    conflicts = await detect_capacity_conflicts(
        db, plan_ids=[plan.id for plan in new_plans]
    )
    return new_plans, pushed, max(0.0, original_qty - total_qty), conflicts
