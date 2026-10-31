"""MRP 快照口径纯函数单测（无 DB）：需求分摊 + 预计量有效期窗口。"""

from datetime import date
from decimal import Decimal

from app.services.mrp.snapshot import (
    allocate_order_remaining,
    is_stale_supply,
    stale_supply_cutoff,
)


def test_allocate_single_line_equals_line_minus_completed():
    # 单行订单：退化为 行量-完成数
    assert allocate_order_remaining([Decimal("1000")], Decimal("300")) == [Decimal("700")]


def test_allocate_multi_line_proportional_not_per_line_subtract():
    # 多行订单：完成数按行占比分摊，而不是每行各减一次表头完成数
    # 23 行共 3977、表头完成 3980 → 整单已交完，各行需求为 0（旧口径会得负数）
    line_qtys = [Decimal("173")] * 23
    allocated = allocate_order_remaining(line_qtys, Decimal("3980"))
    assert sum(allocated, Decimal("0")) == Decimal("0")

    # 2 行共 6944、完成 6544 → 合计剩余 400，按占比分摊
    allocated = allocate_order_remaining([Decimal("5000"), Decimal("1944")], Decimal("6544"))
    assert sum(allocated, Decimal("0")) == Decimal("400")
    expected_share = Decimal("400") * Decimal("5000") / Decimal("6944")
    assert abs(allocated[0] - expected_share) < Decimal("0.001")


def test_allocate_total_conserves_after_rounding():
    # 除法残差修正：合计恒等于剩余量
    allocated = allocate_order_remaining(
        [Decimal("10"), Decimal("1000"), Decimal("990")], Decimal("500")
    )
    assert sum(allocated, Decimal("0")) == Decimal("1500")


def test_allocate_over_completed_clamps_to_total():
    # 完成数超交（负剩余）→ 全 0；完成数为负 → 封顶为行总量
    assert allocate_order_remaining([Decimal("100")], Decimal("150")) == [Decimal("0")]
    allocated = allocate_order_remaining([Decimal("100"), Decimal("100")], Decimal("-40"))
    assert sum(allocated, Decimal("0")) == Decimal("200")


def test_allocate_zero_total_returns_zeros():
    assert allocate_order_remaining([Decimal("0"), Decimal("0")], Decimal("0")) == [Decimal("0"), Decimal("0")]


def test_stale_cutoff_and_filter():
    run_date = date(2026, 9, 29)
    cutoff = stale_supply_cutoff(run_date, 6)
    # 6 个月 ≈ 180 天前
    assert (run_date - cutoff).days == 180
    # 2018-2025 僵尸单 / 上周拖期单 / 无日期单据 三种判定
    assert is_stale_supply(date(2018, 12, 31), cutoff)
    assert is_stale_supply(date(2026, 3, 1), cutoff)
    assert not is_stale_supply(date(2026, 4, 15), cutoff)
    assert not is_stale_supply(None, cutoff)
    # 窗口至少 1 个月
    assert (run_date - stale_supply_cutoff(run_date, 0)).days == 30
