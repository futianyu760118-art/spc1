"""月度产能规划：按出货计划月份汇总订单人时与可用产能（只读）。"""
import json
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.production.monthly_capacity_scenario import MonthlyCapacityScenario
from app.models.production.monthly_schedule_plan import MonthlySchedulePlan
from app.models.production.schedule_plan import ProductionSchedulePlan
from app.schemas.production.monthly_capacity_ai import AiSchedulePlanOut
from app.services.ai import ChatOptions, NotSupportedError, ai_service
from app.services.production.upph_calculation_service import UpphCalculationService

STAGE_LABELS = {
    "assembly": "组装",
    "packaging": "包装",
}
MONTHLY_STAGES = ("assembly", "packaging")


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_integer_quantity(value: Any) -> int:
    quantity = _to_float(value)
    if quantity <= 0:
        return 0
    return max(1, int(round(quantity)))


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def _required_days(hours: float, manpower: float, daily_hours: float) -> Optional[float]:
    capacity = manpower * daily_hours
    if capacity <= 0:
        return None
    return round(hours / capacity, 2)


async def _compute_monthly_capacity_plan(
    db: AsyncSession,
    *,
    year: int,
    month: int,
    stage: str = "all",
    workdays: int = 26,
    daily_hours: float = 12.0,
    assembly_manpower: int = 14,
    packaging_manpower: int = 14,
    include_sunday: bool = False,
    include_scheduled: bool = True,
    keyword: Optional[str] = None,
) -> dict[str, Any]:
    start, end = _month_range(year, month)
    conditions = [
        SaleOrderLine.shipping_plan >= start,
        SaleOrderLine.shipping_plan < end,
        SaleOrderLine.status != "closed",
        SaleOrder.is_deleted == 0,
        SaleOrder.is_closed == 0,
        or_(SaleOrder.erp_status.is_(None), SaleOrder.erp_status != 3),
        or_(
            SaleOrder.completed_qty.is_(None),
            SaleOrder.completed_qty < SaleOrderLine.order_qty,
        ),
        or_(
            SaleOrderLine.bom_no.is_(None),
            ~func.ltrim(SaleOrderLine.bom_no).ilike("Y%"),
        ),
        or_(
            SaleOrderLine.bom_no.is_(None),
            ~func.ltrim(SaleOrderLine.bom_no).ilike("P-%"),
        ),
        # HJY 为样品单，不参与排产
        ~SaleOrderLine.order_no.ilike("HJY%"),
    ]
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                SaleOrderLine.order_no.ilike(like),
                SaleOrderLine.product_code.ilike(like),
                SaleOrderLine.product_name.ilike(like),
                SaleOrderLine.bom_no.ilike(like),
            )
        )

    rows = (
        await db.execute(
            select(
                SaleOrderLine.order_no,
                SaleOrderLine.line_no,
                SaleOrderLine.product_code,
                SaleOrderLine.product_name,
                SaleOrderLine.bom_no,
                SaleOrderLine.order_qty,
                SaleOrderLine.shipping_plan,
                SaleOrderLine.status,
                SaleOrder.completed_qty,
            )
            .join(SaleOrder, SaleOrder.id == SaleOrderLine.sale_order_id)
            .where(*conditions)
            .order_by(
                SaleOrderLine.shipping_plan.asc(),
                SaleOrderLine.order_no.asc(),
                SaleOrderLine.line_no.asc(),
            )
        )
    ).all()

    order_keys = {(str(row.order_no), str(row.line_no)) for row in rows}
    scheduled_keys: set[tuple[str, str]] = set()
    if order_keys:
        order_nos = {key[0] for key in order_keys}
        plan_rows = (
            await db.execute(
                select(ProductionSchedulePlan.order_no, ProductionSchedulePlan.line_no)
                .where(
                    ProductionSchedulePlan.is_active == True,
                    ProductionSchedulePlan.order_no.in_(order_nos),
                )
            )
        ).all()
        scheduled_keys = {
            (str(row[0]), str(row[1]))
            for row in plan_rows
            if (str(row[0]), str(row[1])) in order_keys
        }

    upph_service = UpphCalculationService(db)
    rules_cache: dict[str, dict[str, Any]] = {}
    orders: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    stage_demand = {"assembly": 0.0, "packaging": 0.0}
    stage_prices = {"assembly": 0.0, "packaging": 0.0}

    for row in rows:
        key = (str(row.order_no), str(row.line_no))
        has_schedule = key in scheduled_keys
        if has_schedule and not include_scheduled:
            continue
        qty = _to_float(row.order_qty)
        bom_code = str(row.bom_no or "").strip()
        if qty <= 0:
            missing.append({
                "order_no": row.order_no,
                "line_no": row.line_no,
                "bom_no": bom_code or None,
                "reason": "订单数量为空或为 0",
            })
            continue
        if not bom_code:
            missing.append({
                "order_no": row.order_no,
                "line_no": row.line_no,
                "bom_no": None,
                "reason": "缺少 BOM",
            })
            continue

        rules = rules_cache.get(bom_code)
        if rules is None:
            rules = await upph_service.build_local_stage_rules(bom_code)
            rules_cache[bom_code] = rules

        stage_rules = rules.get("stage_rules") or {}
        assembly_price = _to_float(stage_rules.get("assembly", {}).get("price_total"))
        packaging_price = _to_float(stage_rules.get("packaging", {}).get("price_total"))
        assembly_hour_price = _to_float(stage_rules.get("assembly", {}).get("hour_price"))
        packaging_hour_price = _to_float(stage_rules.get("packaging", {}).get("hour_price"))
        assembly_hours = (
            qty * assembly_price / assembly_hour_price
            if assembly_price > 0 and assembly_hour_price > 0
            else 0.0
        )
        packaging_hours = (
            qty * packaging_price / packaging_hour_price
            if packaging_price > 0 and packaging_hour_price > 0
            else 0.0
        )
        assembly_upph = _to_float(stage_rules.get("assembly", {}).get("upph"))
        packaging_upph = _to_float(stage_rules.get("packaging", {}).get("upph"))

        order_stage_demand = {
            "assembly": round(assembly_hours, 2),
            "packaging": round(packaging_hours, 2),
        }
        for bucket, hours in order_stage_demand.items():
            if stage == "all" or stage == bucket:
                stage_demand[bucket] += hours
                if bucket == "assembly":
                    stage_prices[bucket] += round(qty * assembly_price, 2)
                elif bucket == "packaging":
                    stage_prices[bucket] += round(qty * packaging_price, 2)

        if assembly_hours <= 0 and packaging_hours <= 0:
            missing.append({
                "order_no": row.order_no,
                "line_no": row.line_no,
                "bom_no": bom_code,
                "reason": "缺少有效工价/产能，无法计算人时",
            })

        orders.append({
            "order_no": row.order_no,
            "line_no": row.line_no,
            "product_code": row.product_code,
            "product_name": row.product_name,
            "bom_no": bom_code,
            "shipping_plan": row.shipping_plan.isoformat() if row.shipping_plan else None,
            "quantity": round(qty, 2),
            "status": row.status,
            "schedule_bucket": rules.get("schedule_bucket"),
            "assembly_price": round(assembly_price, 4),
            "packaging_price": round(packaging_price, 4),
            "assembly_upph": round(assembly_upph, 2),
            "packaging_upph": round(packaging_upph, 2),
            "assembly_hours": order_stage_demand["assembly"],
            "packaging_hours": order_stage_demand["packaging"],
            "total_hours": round(sum(order_stage_demand.values()), 2),
            "has_schedule": has_schedule,
        })

    target_dates, _ = _build_preview_workdays(
        year,
        month,
        workdays,
        include_sunday=include_sunday,
        extra_months=0,
    )
    effective_workdays = len(target_dates)
    stage_capacity = {
        "assembly": effective_workdays * assembly_manpower * daily_hours,
        "packaging": effective_workdays * packaging_manpower * daily_hours,
    }
    stage_manpower = {
        "assembly": assembly_manpower,
        "packaging": packaging_manpower,
    }
    stages = []
    selected_stages = [stage] if stage in MONTHLY_STAGES else list(MONTHLY_STAGES)
    for bucket in selected_stages:
        demand = round(stage_demand[bucket], 2)
        available = round(stage_capacity[bucket], 2)
        gap = round(demand - available, 2)
        utilization = round(demand / available * 100, 2) if available > 0 else None
        stages.append({
            "stage": bucket,
            "label": STAGE_LABELS[bucket],
            "workdays": effective_workdays,
            "daily_hours": daily_hours,
            "manpower": stage_manpower[bucket],
            "demand_hours": demand,
            "available_hours": available,
            "utilization": utilization,
            "gap": gap,
            "surplus": round(max(0.0, -gap), 2),
            "required_days_85": _required_days(demand, stage_manpower[bucket], 8.5),
            "required_days_12": _required_days(demand, stage_manpower[bucket], 12.0),
        })

    total_demand = round(sum(item["demand_hours"] for item in stages), 2)
    total_available = round(sum(item["available_hours"] for item in stages), 2)
    total_gap = round(total_demand - total_available, 2)
    required_85 = max((item["required_days_85"] or 0 for item in stages), default=0)
    required_12 = max((item["required_days_12"] or 0 for item in stages), default=0)
    return {
        "year": year,
        "month": month,
        "month_label": f"{year}-{month:02d}",
        "stage": stage,
        "params": {
            "workdays": effective_workdays,
            "workdays_requested": workdays,
            "daily_hours": daily_hours,
            "assembly_manpower": assembly_manpower,
            "packaging_manpower": packaging_manpower,
            "include_sunday": include_sunday,
            "include_scheduled": include_scheduled,
        },
        "summary": {
            "order_count": len(orders),
            "total_quantity": round(sum(item["quantity"] for item in orders), 2),
            "total_prices": {key: round(value, 2) for key, value in stage_prices.items()},
            "demand_hours": total_demand,
            "available_hours": total_available,
            "utilization": round(total_demand / total_available * 100, 2) if total_available > 0 else None,
            "gap": total_gap,
            "surplus": round(max(0.0, -total_gap), 2),
            "required_days_85": required_85,
            "required_days_12": required_12,
        },
        "stages": stages,
        "orders": orders,
        "missing": missing,
    }


_PLAN_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_PLAN_CACHE_TTL_SECONDS = 120


async def get_monthly_capacity_plan(
    db: AsyncSession,
    *,
    year: int,
    month: int,
    stage: str = "all",
    workdays: int = 26,
    daily_hours: float = 12.0,
    assembly_manpower: int = 14,
    packaging_manpower: int = 14,
    include_sunday: bool = False,
    include_scheduled: bool = True,
    keyword: Optional[str] = None,
) -> dict[str, Any]:
    cache_key = (
        year,
        month,
        stage,
        workdays,
        daily_hours,
        assembly_manpower,
        packaging_manpower,
        include_sunday,
        include_scheduled,
        (keyword or "").strip(),
    )
    cached = _PLAN_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _PLAN_CACHE_TTL_SECONDS:
        return cached[1]
    result = await _compute_monthly_capacity_plan(
        db,
        year=year,
        month=month,
        stage=stage,
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        include_sunday=include_sunday,
        include_scheduled=include_scheduled,
        keyword=keyword,
    )
    _PLAN_CACHE[cache_key] = (time.time(), result)
    return result


def _build_preview_workdays(
    year: int,
    month: int,
    workdays: int,
    *,
    include_sunday: bool = False,
    extra_months: int = 2,
) -> tuple[list[date], int]:
    start, end = _month_range(year, month)
    today = date.today()
    cursor = max(start, today) if start <= today < end else start
    target_dates: list[date] = []
    weekday_count = 0
    while cursor < end and weekday_count < workdays:
        if cursor.weekday() != 6:
            weekday_count += 1
        if include_sunday or cursor.weekday() != 6:
            target_dates.append(cursor)
        cursor += timedelta(days=1)

    result = list(target_dates)
    for offset in range(1, extra_months + 1):
        next_year = year + (month - 1 + offset) // 12
        next_month = (month - 1 + offset) % 12 + 1
        cursor, next_end = _month_range(next_year, next_month)
        while cursor < next_end:
            if include_sunday or cursor.weekday() != 6:
                result.append(cursor)
            cursor += timedelta(days=1)
    return result, len(target_dates)


def _next_production_date(target: date, include_sunday: bool = False) -> date:
    current = target + timedelta(days=1)
    while not include_sunday and current.weekday() == 6:
        current += timedelta(days=1)
    return current


def _build_allocation_row(
    order: dict[str, Any],
    *,
    stage: str,
    current_date: date,
    quantity: int,
    hours: float,
    daily_capacity: float,
) -> dict[str, Any]:
    return {
        "date": current_date.isoformat(),
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "order_no": order.get("order_no"),
        "line_no": order.get("line_no"),
        "product_code": order.get("product_code"),
        "shipping_plan": order.get("shipping_plan"),
        "quantity": quantity,
        "hours": round(hours, 2),
        "daily_capacity": round(daily_capacity, 2),
    }


def _append_late_if_needed(
    late: list[dict[str, Any]],
    order: dict[str, Any],
    stage: str,
    last_date: Optional[date],
) -> None:
    if not last_date or not order.get("shipping_plan"):
        return
    try:
        shipping_date = date.fromisoformat(order["shipping_plan"])
    except ValueError:
        return
    if last_date > shipping_date:
        late.append({
            "order_no": order.get("order_no"),
            "line_no": order.get("line_no"),
            "stage": stage,
            "stage_label": STAGE_LABELS[stage],
            "shipping_plan": shipping_date.isoformat(),
            "last_alloc_date": last_date.isoformat(),
            "late_days": (last_date - shipping_date).days,
        })


def _default_sorted_orders(source_orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order_first_date: dict[str, str] = {}
    for item in source_orders:
        order_no = str(item.get("order_no") or "")
        shipping = item.get("shipping_plan") or "9999-12-31"
        if order_no not in order_first_date or shipping < order_first_date[order_no]:
            order_first_date[order_no] = shipping
    return sorted(
        source_orders,
        key=lambda item: (
            order_first_date.get(str(item.get("order_no") or ""), "9999-12-31"),
            str(item.get("order_no") or ""),
            str(item.get("line_no") or ""),
            item.get("shipping_plan") or "9999-12-31",
        ),
    )


def _order_source_orders(
    source_orders: list[dict[str, Any]],
    order_sequence: Optional[list[tuple[str, str]]],
) -> list[dict[str, Any]]:
    """按 AI 给出的订单行顺序重排；缺失的行按默认规则补到末尾，保证不丢单。"""
    if not order_sequence:
        return _default_sorted_orders(source_orders)

    by_key = {
        (str(item.get("order_no") or ""), str(item.get("line_no") or "")): item
        for item in source_orders
    }
    group_rank: dict[str, int] = {}
    groups: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()

    def add(item: dict[str, Any]) -> None:
        key = (str(item.get("order_no") or ""), str(item.get("line_no") or ""))
        if key in seen:
            return
        seen.add(key)
        order_no = key[0]
        if order_no not in group_rank:
            group_rank[order_no] = len(group_rank)
        groups.setdefault(order_no, []).append(item)

    for order_no, line_no in order_sequence:
        item = by_key.get((str(order_no), str(line_no)))
        if item:
            add(item)
    for item in _default_sorted_orders(source_orders):
        add(item)

    ordered: list[dict[str, Any]] = []
    for order_no in sorted(groups, key=lambda value: group_rank[value]):
        ordered.extend(groups[order_no])
    return ordered


def build_daily_allocation_preview(
    plan: dict[str, Any],
    *,
    stage: str,
    workdays: int,
    daily_hours: float,
    assembly_manpower: int,
    packaging_manpower: int,
    include_sunday: bool = False,
    order_sequence: Optional[list[tuple[str, str]]] = None,
) -> dict[str, Any]:
    """按阶段每日容量，把月度订单顺序往后填，仅做预览，不落库。"""
    manpower_by_stage = {
        "assembly": assembly_manpower,
        "packaging": packaging_manpower,
    }
    selected_stages = [stage] if stage in MONTHLY_STAGES else list(MONTHLY_STAGES)
    dates, target_workdays = _build_preview_workdays(
        plan["year"],
        plan["month"],
        workdays,
        include_sunday=include_sunday,
    )
    source_orders = plan.get("orders") or []
    orders = _order_source_orders(source_orders, order_sequence)

    order_groups: list[list[dict[str, Any]]] = []
    for order in orders:
        order_no = str(order.get("order_no") or "")
        if order_groups and str(order_groups[-1][0].get("order_no") or "") == order_no:
            order_groups[-1].append(order)
        else:
            order_groups.append([order])

    allocations: list[dict[str, Any]] = []
    late: list[dict[str, Any]] = []
    unscheduled: list[dict[str, Any]] = []
    daily_used: dict[tuple[str, str], float] = {}
    assembly_end_by_order: dict[str, date] = {}

    epsilon = 1e-6
    for current_stage in selected_stages:
        upph_key = f"{current_stage}_upph"
        daily_capacity = max(1.0, manpower_by_stage[current_stage] * daily_hours)
        day_index = 0
        for group in order_groups:
            order_no = str(group[0].get("order_no") or "")
            lines = []
            for line in group:
                upph = _to_float(line.get(upph_key))
                quantity = _resolve_integer_quantity(line.get("quantity"))
                if upph > 0 and quantity > 0:
                    lines.append((line, upph, quantity))
            if not lines:
                continue
            if current_stage == "packaging":
                assembly_end = assembly_end_by_order.get(order_no)
                if assembly_end:
                    required_start = _next_production_date(assembly_end, include_sunday=include_sunday)
                    while day_index < len(dates) and dates[day_index] < required_start:
                        day_index += 1

            group_hours = sum(quantity / upph for _, upph, quantity in lines)
            chosen_index = None
            for index in range(day_index, len(dates)):
                used = daily_used.get((dates[index].isoformat(), current_stage), 0.0)
                if daily_capacity - used + epsilon >= group_hours:
                    chosen_index = index
                    break

            order_last_date = None
            if chosen_index is not None:
                day_index = chosen_index
                current_date = dates[day_index]
                key = (current_date.isoformat(), current_stage)
                used = daily_used.get(key, 0.0)
                for line, upph, quantity in lines:
                    hours = quantity / upph
                    allocations.append(_build_allocation_row(
                        line,
                        stage=current_stage,
                        current_date=current_date,
                        quantity=quantity,
                        hours=hours,
                        daily_capacity=daily_capacity,
                    ))
                    used += hours
                    _append_late_if_needed(late, line, current_stage, current_date)
                daily_used[key] = used
                order_last_date = current_date
            else:
                for line, upph, quantity in lines:
                    remaining = quantity
                    line_last_date = None
                    while remaining > 0:
                        if day_index >= len(dates):
                            unscheduled.append({
                                "order_no": line.get("order_no"),
                                "line_no": line.get("line_no"),
                                "stage": current_stage,
                                "remaining_quantity": remaining,
                                "remaining_hours": round(remaining / upph, 2),
                                "reason": "月度工作日产能不足",
                            })
                            break
                        current_date = dates[day_index]
                        key = (current_date.isoformat(), current_stage)
                        used = daily_used.get(key, 0.0)
                        available = daily_capacity - used
                        max_quantity = int(available * upph + epsilon) if available > epsilon else 0
                        if max_quantity <= 0:
                            day_index += 1
                            continue
                        take = min(remaining, max_quantity)
                        hours = take / upph
                        allocations.append(_build_allocation_row(
                            line,
                            stage=current_stage,
                            current_date=current_date,
                            quantity=take,
                            hours=hours,
                            daily_capacity=daily_capacity,
                        ))
                        daily_used[key] = used + hours
                        remaining -= take
                        line_last_date = current_date
                        if remaining > 0:
                            day_index += 1
                    if line_last_date:
                        _append_late_if_needed(late, line, current_stage, line_last_date)
                        if order_last_date is None or line_last_date > order_last_date:
                            order_last_date = line_last_date
            if current_stage == "assembly" and order_last_date:
                assembly_end_by_order[order_no] = order_last_date

    daily: list[dict[str, Any]] = []
    for current_date in dates:
        for current_stage in selected_stages:
            used = round(daily_used.get((current_date.isoformat(), current_stage), 0.0), 2)
            capacity = round(manpower_by_stage[current_stage] * daily_hours, 2)
            if used <= 0:
                continue
            daily.append({
                "date": current_date.isoformat(),
                "stage": current_stage,
                "stage_label": STAGE_LABELS[current_stage],
                "capacity_hours": capacity,
                "allocated_hours": used,
                "utilization": round(used / capacity * 100, 2) if capacity > 0 else None,
                "orders": [
                    item for item in allocations
                    if item["date"] == current_date.isoformat() and item["stage"] == current_stage
                ],
            })

    return {
        "stage": stage,
        "workdays": target_workdays,
        "allocation_days": len(dates),
        "overflow_days": max(0, len(dates) - target_workdays),
        "dates": [item.isoformat() for item in dates],
        "allocations": allocations,
        "daily": daily,
        "late": late,
        "unscheduled": unscheduled,
    }

async def generate_monthly_schedule_plans(
    db: AsyncSession,
    *,
    year: int,
    month: int,
    workdays: int,
    daily_hours: float,
    assembly_manpower: int,
    packaging_manpower: int,
    operator: str,
    include_sunday: bool = False,
    include_scheduled: bool = True,
    order_sequence: Optional[list[tuple[str, str]]] = None,
    scheme_label: str = "月度排产方案",
) -> dict[str, Any]:
    """把每日分配预览落成独立的月度排产方案（不碰原排产表）。"""
    plan = await get_monthly_capacity_plan(
        db,
        year=year,
        month=month,
        stage="all",
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        include_sunday=include_sunday,
        include_scheduled=include_scheduled,
    )
    preview = build_daily_allocation_preview(
        plan,
        stage="all",
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        include_sunday=include_sunday,
        order_sequence=order_sequence,
    )
    order_map = {
        (str(item["order_no"]), str(item["line_no"])): item
        for item in plan.get("orders") or []
    }
    manpower_by_stage = {
        "assembly": assembly_manpower,
        "packaging": packaging_manpower,
    }
    batch_no = datetime.now().strftime("MS%Y%m%d%H%M%S")
    schedule_month = f"{year}-{month:02d}"

    await db.execute(
        MonthlySchedulePlan.__table__.update()
        .where(
            MonthlySchedulePlan.schedule_month == schedule_month,
            MonthlySchedulePlan.is_active == True,
        )
        .values(is_active=False)
    )

    created: list[dict[str, Any]] = []
    for allocation in preview.get("allocations") or []:
        key = (str(allocation["order_no"]), str(allocation["line_no"]))
        order = order_map.get(key)
        if not order:
            continue
        stage = str(allocation["stage"])
        upph = _to_float(order.get(f"{stage}_upph"))
        quantity = _resolve_integer_quantity(allocation.get("quantity"))
        if upph <= 0 or quantity <= 0:
            continue
        created.append({
            "order_no": key[0],
            "line_no": key[1],
            "stage": stage,
            "plan_date": allocation["date"],
            "quantity": quantity,
            "upph": upph,
            "source_qty": _to_float(order.get("quantity")),
            "order": order,
        })

    plan_rows: list[MonthlySchedulePlan] = []
    for item in created:
        order = item["order"]
        plan_date = date.fromisoformat(item["plan_date"])
        price_total = (
            _to_float(order.get("assembly_price"))
            if item["stage"] == "assembly"
            else _to_float(order.get("packaging_price"))
            if item["stage"] == "packaging"
            else None
        )
        promised = None
        if order.get("shipping_plan"):
            try:
                promised = date.fromisoformat(order["shipping_plan"])
            except ValueError:
                promised = None
        plan_rows.append(MonthlySchedulePlan(
            schedule_month=schedule_month,
            batch_no=batch_no,
            order_no=item["order_no"],
            line_no=item["line_no"],
            product_code=order.get("product_code"),
            product_name=order.get("product_name"),
            bom_no=order.get("bom_no"),
            department="生产",
            schedule_bucket=item["stage"],
            quantity=item["quantity"],
            upph=item["upph"],
            manpower=manpower_by_stage[item["stage"]],
            daily_work_hours=daily_hours,
            plan_date=plan_date,
            start_date=plan_date,
            end_date=plan_date,
            source_order_qty=item["source_qty"],
            source_promised_date=promised,
            price_total=price_total,
            status="planned",
            remark=scheme_label,
            is_active=True,
            created_by=operator,
        ))
    db.add_all(plan_rows)
    await db.flush()
    return {
        "batch_no": batch_no,
        "schedule_month": schedule_month,
        "created_count": len(plan_rows),
        "late_count": len(preview.get("late") or []),
        "unscheduled_count": len(preview.get("unscheduled") or []),
    }


AI_SCHEDULE_MAX_LINES = 400


def _collect_ai_schedulable_lines(plan: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    selected_stages = [stage] if stage in MONTHLY_STAGES else list(MONTHLY_STAGES)
    lines: list[dict[str, Any]] = []
    for item in plan.get("orders") or []:
        quantity = _resolve_integer_quantity(item.get("quantity"))
        if quantity <= 0:
            continue
        if not any(_to_float(item.get(f"{bucket}_upph")) > 0 for bucket in selected_stages):
            continue
        line = {
            "order_no": str(item.get("order_no") or ""),
            "line_no": str(item.get("line_no") or ""),
            "product_code": item.get("product_code"),
            "shipping_plan": item.get("shipping_plan"),
            "quantity": quantity,
        }
        for bucket in MONTHLY_STAGES:
            line[f"{bucket}_hours"] = round(_to_float(item.get(f"{bucket}_hours")), 2)
            line[f"{bucket}_upph"] = round(_to_float(item.get(f"{bucket}_upph")), 2)
        lines.append(line)
    return lines


def _build_ai_schedule_prompt(
    plan: dict[str, Any],
    lines: list[dict[str, Any]],
    *,
    workdays: int,
    daily_hours: float,
    assembly_manpower: int,
    packaging_manpower: int,
) -> str:
    payload = {
        "period": plan.get("month_label"),
        "workdays": workdays,
        "daily_hours": daily_hours,
        "stage_daily_capacity_hours": {
            "assembly": round(assembly_manpower * daily_hours, 2),
            "packaging": round(packaging_manpower * daily_hours, 2),
        },
        "lines": lines,
    }
    return (
        "你是制造业月度排产优化专家。请根据订单行明细与各阶段日产能，给出组装、包装的订单行排产先后顺序，"
        "目标是把延期订单数量降到最低。\n\n"
        "【硬约束】\n"
        "- 只能对输入 lines 中出现的 order_no / line_no 排序，不得新增或臆造订单行。\n"
        "- 同一订单的多行必须连续出现，保证同一订单整体优先完成。\n"
        "- order_sequence 需覆盖全部输入行且每行只出现一次；若行数过多，按优先级给出尽可能完整的顺序。\n"
        "- 交期越早越靠前；同交期时人时大的优先；没有交期的排在最后。\n\n"
        "【输出要求】\n"
        "- 必须输出纯 JSON，第一个字符是 '{'，最后一个字符是 '}'，不要使用 markdown 代码块或说明文字。\n"
        "- summary: 80 字以内说明本次排序思路。\n"
        "- order_sequence: 按排产先后排列的 [{order_no, line_no}] 数组。\n"
        "- risks: 可能的风险点（如产能不足、交期集中）字符串数组。\n\n"
        "【输入数据】\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def _normalize_ai_order_sequence(
    raw_sequence: list[tuple[str, str]],
    source_orders: list[dict[str, Any]],
) -> tuple[list[tuple[str, str]], int, int]:
    """校验 AI 顺序：丢弃臆造/重复行，缺失行按默认交期顺序补到末尾。"""
    by_key = {
        (str(item.get("order_no") or ""), str(item.get("line_no") or ""))
        for item in source_orders
    }
    normalized: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    matched_count = 0
    for order_no, line_no in raw_sequence:
        key = (str(order_no), str(line_no))
        if key in by_key and key not in seen:
            normalized.append(key)
            seen.add(key)
            matched_count += 1
    appended_count = 0
    for item in _default_sorted_orders(source_orders):
        key = (str(item.get("order_no") or ""), str(item.get("line_no") or ""))
        if key not in seen:
            normalized.append(key)
            seen.add(key)
            appended_count += 1
    return normalized, matched_count, appended_count


async def get_ai_allocation_preview(
    db: AsyncSession,
    *,
    year: int,
    month: int,
    stage: str = "all",
    workdays: int = 26,
    daily_hours: float = 12.0,
    assembly_manpower: int = 14,
    packaging_manpower: int = 14,
    include_sunday: bool = False,
    include_scheduled: bool = True,
    keyword: Optional[str] = None,
) -> dict[str, Any]:
    """调用大模型决定订单行排产顺序，再用确定性容量算法生成每日预览。"""
    plan = await get_monthly_capacity_plan(
        db,
        year=year,
        month=month,
        stage=stage,
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        include_sunday=include_sunday,
        include_scheduled=include_scheduled,
        keyword=keyword,
    )
    schedulable_lines = _collect_ai_schedulable_lines(plan, stage)
    if not schedulable_lines:
        raise ValueError("当前条件下没有可排产的订单行，无法生成 AI 排产")

    prompt = _build_ai_schedule_prompt(
        plan,
        schedulable_lines[:AI_SCHEDULE_MAX_LINES],
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
    )
    try:
        ai_plan = await ai_service.structured_output(
            prompt,
            AiSchedulePlanOut,
            ChatOptions(temperature=0.2, max_tokens=8192, timeout=120),
        )
    except NotSupportedError:
        raise HTTPException(
            status_code=400,
            detail=(
                "AI 服务未配置（当前 provider=rule_based，无法生成真实排产方案）。"
                "请在后端 .env.local 设置 AI_DEFAULT_PROVIDER=openai 或 dashscope，"
                "并配置对应的 API key 与 base_url 后重启服务再重试。"
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 排产失败: {exc}")

    raw_sequence = [(item.order_no, item.line_no) for item in ai_plan.order_sequence]
    sequence, matched_count, appended_count = _normalize_ai_order_sequence(
        raw_sequence, schedulable_lines
    )
    preview = build_daily_allocation_preview(
        plan,
        stage=stage,
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        include_sunday=include_sunday,
        order_sequence=sequence,
    )
    return {
        "summary": plan.get("summary"),
        "stages": plan.get("stages"),
        **preview,
        "ai": {
            "provider": ai_service.current_provider(),
            "summary": ai_plan.summary,
            "risks": ai_plan.risks,
            "order_sequence": [
                {"order_no": order_no, "line_no": line_no}
                for order_no, line_no in sequence
            ],
            "matched_count": matched_count,
            "appended_count": appended_count,
        },
    }


def _serialize_monthly_plan(plan: MonthlySchedulePlan) -> dict[str, Any]:
    required_hours = None
    if plan.quantity and plan.upph and plan.manpower:
        required_hours = round(float(plan.quantity) / (float(plan.upph) * int(plan.manpower)), 2)
    return {
        "id": plan.id,
        "schedule_month": plan.schedule_month,
        "batch_no": plan.batch_no,
        "is_active": bool(plan.is_active),
        "order_no": plan.order_no,
        "line_no": plan.line_no,
        "product_code": plan.product_code,
        "product_name": plan.product_name,
        "bom_no": plan.bom_no,
        "schedule_bucket": plan.schedule_bucket,
        "quantity": float(plan.quantity or 0),
        "upph": float(plan.upph or 0),
        "manpower": int(plan.manpower or 0),
        "daily_work_hours": float(plan.daily_work_hours or 0),
        "required_hours": required_hours,
        "plan_date": plan.plan_date.isoformat() if plan.plan_date else None,
        "source_order_qty": float(plan.source_order_qty) if plan.source_order_qty is not None else None,
        "source_promised_date": plan.source_promised_date.isoformat() if plan.source_promised_date else None,
        "status": plan.status,
        "remark": plan.remark,
    }


async def list_monthly_schedule_plans(
    db: AsyncSession,
    *,
    year: int,
    month: int,
    stage: Optional[str] = None,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
    keyword: Optional[str] = None,
    batch_no: Optional[str] = None,
) -> list[dict[str, Any]]:
    schedule_month = f"{year}-{month:02d}"
    conditions = [MonthlySchedulePlan.schedule_month == schedule_month]
    if batch_no:
        conditions.append(MonthlySchedulePlan.batch_no == batch_no)
    else:
        conditions.append(MonthlySchedulePlan.is_active == True)
    if stage and stage != "all":
        conditions.append(MonthlySchedulePlan.schedule_bucket == stage)
    if date_start:
        conditions.append(MonthlySchedulePlan.plan_date >= date_start)
    if date_end:
        conditions.append(MonthlySchedulePlan.plan_date <= date_end)
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                MonthlySchedulePlan.order_no.ilike(like),
                MonthlySchedulePlan.product_code.ilike(like),
                MonthlySchedulePlan.bom_no.ilike(like),
            )
        )
    rows = (
        await db.execute(
            select(MonthlySchedulePlan)
            .where(*conditions)
            .order_by(
                MonthlySchedulePlan.plan_date.asc(),
                MonthlySchedulePlan.order_no.asc(),
                MonthlySchedulePlan.line_no.asc(),
                MonthlySchedulePlan.schedule_bucket.asc(),
            )
        )
    ).scalars().all()
    items = [_serialize_monthly_plan(row) for row in rows]
    # 按实际排产顺序展示：日期优先、同一天按计划创建顺序（生成时即排产顺序），
    # 避免按订单号排序造成“订单未排完却先排了别的订单”的错觉。
    items.sort(
        key=lambda item: (
            item["plan_date"] or "9999-12-31",
            item["id"],
        )
    )
    return items


async def list_monthly_schedule_batches(
    db: AsyncSession,
    *,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    schedule_month = f"{year}-{month:02d}"
    rows = (
        await db.execute(
            select(MonthlySchedulePlan)
            .where(
                MonthlySchedulePlan.schedule_month == schedule_month,
                MonthlySchedulePlan.batch_no.isnot(None),
            )
            .order_by(MonthlySchedulePlan.created_at.desc())
        )
    ).scalars().all()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        batch_no = str(row.batch_no)
        item = grouped.setdefault(batch_no, {
            "batch_no": batch_no,
            "schedule_month": schedule_month,
            "is_active": False,
            "row_count": 0,
            "order_nos": set(),
            "quantity_total": 0.0,
            "date_start": None,
            "date_end": None,
            "created_by": None,
            "created_at": None,
        })
        item["row_count"] += 1
        item["order_nos"].add(row.order_no)
        item["quantity_total"] += _to_float(row.quantity)
        item["is_active"] = item["is_active"] or bool(row.is_active)
        if row.plan_date:
            plan_date = row.plan_date.isoformat()
            if not item["date_start"] or plan_date < item["date_start"]:
                item["date_start"] = plan_date
            if not item["date_end"] or plan_date > item["date_end"]:
                item["date_end"] = plan_date
        if row.created_by and not item["created_by"]:
            item["created_by"] = row.created_by
        if row.created_at and not item["created_at"]:
            item["created_at"] = row.created_at.isoformat()

    result = []
    for item in grouped.values():
        item["order_count"] = len(item.pop("order_nos"))
        item["quantity_total"] = round(item.pop("quantity_total"), 2)
        result.append(item)
    result.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return result


async def activate_monthly_schedule_batch(
    db: AsyncSession,
    *,
    year: int,
    month: int,
    batch_no: str,
) -> dict[str, Any]:
    schedule_month = f"{year}-{month:02d}"
    rows = (
        await db.execute(
            select(MonthlySchedulePlan).where(
                MonthlySchedulePlan.schedule_month == schedule_month,
                MonthlySchedulePlan.batch_no == batch_no,
            )
        )
    ).scalars().all()
    if not rows:
        raise ValueError("排产批次不存在")

    await db.execute(
        MonthlySchedulePlan.__table__.update()
        .where(
            MonthlySchedulePlan.schedule_month == schedule_month,
            MonthlySchedulePlan.is_active == True,
        )
        .values(is_active=False)
    )
    await db.execute(
        MonthlySchedulePlan.__table__.update()
        .where(
            MonthlySchedulePlan.schedule_month == schedule_month,
            MonthlySchedulePlan.batch_no == batch_no,
        )
        .values(is_active=True)
    )
    await db.flush()
    return {"batch_no": batch_no, "activated_count": len(rows)}


async def _apply_schedule_bucket(
    db: AsyncSession,
    plan: MonthlySchedulePlan,
    schedule_bucket: str,
) -> None:
    if schedule_bucket == plan.schedule_bucket:
        return
    bom_code = str(plan.bom_no or "").strip()
    if not bom_code:
        raise ValueError("该计划缺少 BOM，无法调整阶段")
    rules = await UpphCalculationService(db).build_local_stage_rules(bom_code)
    stage_rule = (rules.get("stage_rules") or {}).get(schedule_bucket) or {}
    upph = _to_float(stage_rule.get("upph"))
    price_total = _to_float(stage_rule.get("price_total"))
    if upph <= 0:
        raise ValueError(f"该 BOM 缺少{STAGE_LABELS[schedule_bucket]}阶段 UPPH，无法调整阶段")
    scenario = await db.get(MonthlyCapacityScenario, 1)
    manpower = getattr(scenario, f"{schedule_bucket}_manpower", None) if scenario else None
    plan.schedule_bucket = schedule_bucket
    plan.upph = upph
    plan.price_total = price_total
    if manpower:
        plan.manpower = int(manpower)


async def update_monthly_schedule_plan(
    db: AsyncSession,
    *,
    plan_id: int,
    plan_date: Optional[date] = None,
    daily_work_hours: Optional[float] = None,
    schedule_bucket: Optional[str] = None,
) -> dict[str, Any]:
    plan = await db.get(MonthlySchedulePlan, plan_id)
    if not plan or not plan.is_active:
        raise ValueError("月度排产计划不存在或已失效")
    if plan_date:
        plan.plan_date = plan_date
        plan.start_date = plan_date
        plan.end_date = plan_date
    if daily_work_hours is not None:
        if daily_work_hours < 1 or daily_work_hours > 24:
            raise ValueError("每天工作时长必须在 1-24 小时之间")
        plan.daily_work_hours = daily_work_hours
    if schedule_bucket:
        await _apply_schedule_bucket(db, plan, schedule_bucket)
    await db.flush()

    required_hours = (
        float(plan.quantity) / (float(plan.upph) * int(plan.manpower))
        if plan.quantity and plan.upph and plan.manpower
        else 0
    )
    same_day_hours = (
        await db.execute(
            select(func.coalesce(func.sum(
                MonthlySchedulePlan.quantity / (MonthlySchedulePlan.upph * MonthlySchedulePlan.manpower)
            ), 0))
            .where(
                MonthlySchedulePlan.schedule_month == plan.schedule_month,
                MonthlySchedulePlan.is_active == True,
                MonthlySchedulePlan.schedule_bucket == plan.schedule_bucket,
                MonthlySchedulePlan.plan_date == plan.plan_date,
                MonthlySchedulePlan.id != plan.id,
            )
        )
    ).scalar() or 0
    warning = None
    if round(float(same_day_hours) + required_hours, 2) > float(plan.daily_work_hours or 0) + 0.01:
        warning = "当天该阶段计划工时已超过设定日工时，请检查"
    data = _serialize_monthly_plan(plan)
    data["warning"] = warning
    return data
