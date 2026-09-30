"""MRP 净算与批量取整单测（无 DB）。"""

from datetime import date, timedelta
from decimal import Decimal

from app.services.mrp.netting import (
    DemandEvent,
    SupplyEvent,
    net_requirements,
    round_by_policy,
)

D0 = date(2026, 9, 24)


def test_round_by_policy_lot_for_lot_with_moq():
    assert round_by_policy(Decimal("3"), Decimal("10"), "lot_for_lot", None) == Decimal("10")
    assert round_by_policy(Decimal("12"), Decimal("10"), "lot_for_lot", None) == Decimal("12")


def test_round_by_policy_multiple_ceiling():
    assert round_by_policy(Decimal("12"), None, "multiple", Decimal("5")) == Decimal("15")


def test_round_by_policy_moq_then_multiple():
    # 先取 MOQ 下限(7)，再取整到批量 5 的倍数 → 10
    assert round_by_policy(Decimal("1"), Decimal("7"), "multiple", Decimal("5")) == Decimal("10")


def test_net_inventory_covers_no_suggestion():
    buckets, plans = net_requirements(
        Decimal("100"), Decimal("0"),
        [DemandEvent(D0, Decimal("60"))], [],
    )
    assert plans == []
    assert buckets[-1].closing_qty == Decimal("40")


def test_net_gap_generates_suggestion_and_backfill():
    buckets, plans = net_requirements(
        Decimal("10"), Decimal("0"),
        [DemandEvent(D0, Decimal("30"))], [],
    )
    assert len(plans) == 1
    assert plans[0].qty == Decimal("20")
    assert plans[0].need_date == D0
    assert plans[0].source == "demand"
    assert buckets[-1].net_demand_qty == Decimal("20")
    assert buckets[-1].closing_qty == Decimal("0")


def test_safety_stock_top_up_only_when_below():
    # 库存 100 > 安全库存 20：不产生建议
    _, plans = net_requirements(Decimal("100"), Decimal("20"), [DemandEvent(D0, Decimal("50"))], [])
    assert plans == []
    # 库存 15 < 安全库存 20：补足到 20，缺口 5
    _, plans2 = net_requirements(Decimal("15"), Decimal("20"), [DemandEvent(D0, Decimal("0"))], [])
    # 需求为 0 的事件仍会检查水位：可用 15 < 20 → gap 5，source=safety_stock
    assert len(plans2) == 1 and plans2[0].qty == Decimal("5") and plans2[0].source == "safety_stock"


def test_supply_before_demand_covers():
    d5 = D0 + timedelta(days=5)
    buckets, plans = net_requirements(
        Decimal("0"), Decimal("0"),
        [DemandEvent(D0, Decimal("30"))],
        [SupplyEvent(d5, Decimal("30"), "po")],
    )
    # 需求在 day0，供给在 day5 → day0 缺口 30 → 建议 30
    assert len(plans) == 1 and plans[0].qty == Decimal("30")
    assert buckets[0].net_demand_qty == Decimal("30")


def test_batch_rounding_residue_rolls_forward():
    d1 = D0 + timedelta(days=1)
    buckets, plans = net_requirements(
        Decimal("0"), Decimal("0"),
        [DemandEvent(D0, Decimal("12"))],
        [],
        moq=None, batch_policy="multiple", batch_qty=Decimal("5"),
    )
    # 缺口 12 → 取整 15；多余额 3 滚入后续桶（本用例仅一桶，期末=3）
    assert plans[0].qty == Decimal("15")
    assert buckets[0].closing_qty == Decimal("3")
