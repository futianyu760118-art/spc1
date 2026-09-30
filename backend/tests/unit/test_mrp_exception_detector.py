"""MRP 例外检测纯函数单测（无 DB）。"""

from datetime import date
from decimal import Decimal

from app.services.mrp.exception_detector import (
    EXC_PAST_DUE_DEMAND,
    EXC_PAST_DUE_SUPPLY,
    EXC_SUPPLY_CANCEL,
    EXC_SUPPLY_EARLY,
    EXC_SUPPLY_LATE,
    EXC_SUPPLY_REDUCE,
    DemandInfo,
    SupplyInfo,
    detect_material_exceptions,
)

RUN = date(2026, 9, 24)


def _supply(d, qty, source_type="purchase_order", doc_no="PO-1", line_no="1", source_id=11):
    return SupplyInfo(
        date=d, qty=Decimal(qty), source_type=source_type,
        doc_no=doc_no, line_no=line_no, source_id=source_id,
    )


def _demand(d, qty, order_no="SO-1", line_no="1"):
    return DemandInfo(need_date=d, qty=Decimal(qty), order_no=order_no, line_no=line_no)


def _detect(supplies, demands, grace=2):
    return detect_material_exceptions(
        material_id=1, material_code="M-001", material_name="测试物料",
        supplies=supplies, demands=demands, grace_days=grace, run_date=RUN,
    )


def test_supply_late_beyond_grace_suggests_advance():
    supply = _supply(date(2026, 10, 10), "100")
    demand = _demand(date(2026, 9, 30), "100")
    payloads = _detect([supply], [demand], grace=2)
    assert len(payloads) == 1
    p = payloads[0]
    assert p["exception_code"] == EXC_SUPPLY_LATE
    assert p["exception_type"] == "supply_late"
    assert p["need_date"] == date(2026, 9, 30)
    assert p["doc_date"] == date(2026, 10, 10)
    assert p["adjust_days"] == -10
    assert p["suggest_date"] == date(2026, 9, 30)
    assert "建议提前" in p["detail"]


def test_supply_early_beyond_grace_suggests_postpone():
    supply = _supply(date(2026, 9, 25), "100")
    demand = _demand(date(2026, 10, 20), "100")
    payloads = _detect([supply], [demand], grace=2)
    assert len(payloads) == 1
    p = payloads[0]
    assert p["exception_code"] == EXC_SUPPLY_EARLY
    assert p["exception_type"] == "supply_early"
    assert p["need_date"] == date(2026, 10, 20)
    assert p["adjust_days"] == 25
    assert p["suggest_date"] == date(2026, 10, 20)
    assert "建议延后" in p["detail"]


def test_within_grace_no_reschedule_exception():
    supply = _supply(date(2026, 9, 26), "100")
    demand = _demand(date(2026, 9, 28), "100")
    assert _detect([supply], [demand], grace=3) == []
    # 偏差等于宽限期（非“超过”）也不产生例外
    assert _detect([supply], [demand], grace=2) == []


def test_uncovered_supply_yields_cancel_exception():
    payloads = _detect([_supply(date(2026, 9, 25), "50")], [], grace=2)
    assert len(payloads) == 1
    p = payloads[0]
    assert p["exception_code"] == EXC_SUPPLY_CANCEL
    assert p["exception_type"] == "supply_excess"
    assert p["suggest_qty"] == Decimal("50")
    assert "建议取消" in p["detail"]


def test_partial_coverage_yields_reduce_with_remainder_qty():
    supply = _supply(date(2026, 9, 30), "150")
    demand = _demand(date(2026, 9, 30), "100")
    payloads = _detect([supply], [demand], grace=2)
    assert len(payloads) == 1
    p = payloads[0]
    assert p["exception_code"] == EXC_SUPPLY_REDUCE
    assert p["exception_type"] == "supply_excess"
    assert p["suggest_qty"] == Decimal("50")
    assert "建议减量" in p["detail"]


def test_past_due_demand_flagged():
    payloads = _detect([], [_demand(date(2026, 9, 20), "10")], grace=2)
    assert len(payloads) == 1
    p = payloads[0]
    assert p["exception_code"] == EXC_PAST_DUE_DEMAND
    assert p["exception_type"] == "past_due_demand"
    assert p["source_type"] == "sale_order_line"
    assert p["need_date"] == date(2026, 9, 20)
    assert p["suggest_qty"] == Decimal("10")


def test_past_due_supply_flagged():
    supply = _supply(date(2026, 9, 20), "10")
    demand = _demand(date(2026, 9, 24), "10")
    payloads = _detect([supply], [demand], grace=5)
    assert len(payloads) == 1
    p = payloads[0]
    assert p["exception_code"] == EXC_PAST_DUE_SUPPLY
    assert p["exception_type"] == "past_due_supply"
    assert p["doc_date"] == date(2026, 9, 20)
    assert p["suggest_qty"] == Decimal("10")


def test_multi_demand_fifo_late_classified_by_earliest():
    supply = _supply(date(2026, 10, 1), "100")
    demands = [
        _demand(date(2026, 9, 26), "40", order_no="SO-A"),
        _demand(date(2026, 10, 20), "60", order_no="SO-B"),
    ]
    payloads = _detect([supply], demands, grace=2)
    # 单个供给恰好覆盖两需求（40+60），无余量例外
    assert [p["exception_code"] for p in payloads] == [EXC_SUPPLY_LATE]
    p = payloads[0]
    assert p["need_date"] == date(2026, 9, 26)
    assert p["adjust_days"] == -5


def test_multi_demand_fifo_early_classified_by_latest():
    supply = _supply(date(2026, 9, 27), "100")
    demands = [
        _demand(date(2026, 9, 26), "40", order_no="SO-A"),
        _demand(date(2026, 10, 20), "60", order_no="SO-B"),
    ]
    payloads = _detect([supply], demands, grace=2)
    # 相对最早需求仅晚 1 天（宽限内），相对最晚需求早 23 天 → 取最晚需求建议延后
    assert [p["exception_code"] for p in payloads] == [EXC_SUPPLY_EARLY]
    p = payloads[0]
    assert p["need_date"] == date(2026, 10, 20)
    assert p["adjust_days"] == 23
