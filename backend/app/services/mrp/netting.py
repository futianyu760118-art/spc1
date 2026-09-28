"""MRP 日桶净需求平衡（纯函数，便于单测）。"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional

_ZERO = Decimal("0")


@dataclass(frozen=True)
class DemandEvent:
    need_date: date
    qty: Decimal
    pegging: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class SupplyEvent:
    supply_date: date
    qty: Decimal
    source_type: str


@dataclass
class BucketRow:
    bucket_date: date
    opening_qty: Decimal
    gross_demand_qty: Decimal
    supply_by_type: dict[str, Decimal]
    substitute_in_qty: Decimal
    substitute_out_qty: Decimal
    safety_stock_qty: Decimal
    closing_qty: Decimal
    net_demand_qty: Decimal
    pegging: list[dict]


@dataclass(frozen=True)
class PlannedOrder:
    need_date: date
    qty: Decimal
    source: str  # demand / safety_stock
    pegging: list[dict]


def round_by_policy(gap: Decimal, moq: Optional[Decimal], batch_policy: str, batch_qty: Optional[Decimal]) -> Decimal:
    qty = gap
    if moq and qty < moq:
        qty = moq
    if batch_policy in ("multiple", "fixed") and batch_qty and batch_qty > 0:
        qty = (qty / batch_qty).to_integral_value(rounding="ROUND_CEILING") * batch_qty
    return qty


def net_requirements(
    opening_qty: Decimal,
    safety_stock: Decimal,
    demands: Iterable[DemandEvent],
    supplies: Iterable[SupplyEvent],
    moq: Optional[Decimal] = None,
    batch_policy: str = "lot_for_lot",
    batch_qty: Optional[Decimal] = None,
) -> tuple[list[BucketRow], list[PlannedOrder]]:
    demand_by_date: dict[date, list[DemandEvent]] = {}
    for d in demands:
        demand_by_date.setdefault(d.need_date, []).append(d)
    supply_by_date: dict[date, list[SupplyEvent]] = {}
    for s in supplies:
        supply_by_date.setdefault(s.supply_date, []).append(s)

    event_dates = sorted(set(demand_by_date) | set(supply_by_date))
    buckets: list[BucketRow] = []
    per_bucket_plans: list[tuple[date, Decimal, bool, list[dict]]] = []
    available = opening_qty

    for event_date in event_dates:
        opening = available
        supply_map: dict[str, Decimal] = {}
        for s in supply_by_date.get(event_date, []):
            supply_map[s.source_type] = supply_map.get(s.source_type, _ZERO) + s.qty
        supply_total = sum(supply_map.values(), _ZERO)
        day_demands = demand_by_date.get(event_date, [])
        gross = sum((d.qty for d in day_demands), _ZERO)
        pegging: list[dict] = []
        for d in day_demands:
            pegging.extend(d.pegging)

        available = opening + supply_total - gross
        net_demand = _ZERO
        if available < safety_stock:
            net_demand = safety_stock - available
            planned = round_by_policy(net_demand, moq, batch_policy, batch_qty)
            available += planned
            per_bucket_plans.append((event_date, planned, gross == 0, pegging))

        buckets.append(
            BucketRow(
                bucket_date=event_date,
                opening_qty=opening,
                gross_demand_qty=gross,
                supply_by_type=supply_map,
                substitute_in_qty=_ZERO,
                substitute_out_qty=_ZERO,
                safety_stock_qty=safety_stock,
                closing_qty=available,
                net_demand_qty=net_demand,
                pegging=pegging,
            )
        )

    if not per_bucket_plans:
        return buckets, []

    total_qty = sum((p[1] for p in per_bucket_plans), _ZERO)
    earliest = per_bucket_plans[0][0]
    all_safety_only = all(p[2] for p in per_bucket_plans)
    merged_pegging: list[dict] = []
    for _, _, _, peg in per_bucket_plans:
        merged_pegging.extend(peg)
    suggestion = PlannedOrder(
        need_date=earliest,
        qty=total_qty,
        source="safety_stock" if all_safety_only else "demand",
        pegging=merged_pegging,
    )
    return buckets, [suggestion]
