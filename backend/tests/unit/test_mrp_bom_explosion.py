"""低位码与 BOM 展开纯函数单测（无 DB）。"""

from datetime import date, timedelta
from decimal import Decimal

from app.services.mrp.bom_explosion import (
    BomComponent,
    compute_low_level_codes,
    component_valid_at,
    explode,
    flatten_phantom,
)


def _comp(mid, qty, scrap="0", offset=0, valid=None, invalid=None, base="1"):
    return BomComponent(
        material_id=mid,
        standard_qty=Decimal(qty),
        scrap_rate=Decimal(scrap),
        lead_offset_days=offset,
        valid_date=valid,
        invalid_date=invalid,
        base_qty=Decimal(base),
    )


def test_component_valid_at_bounds():
    d = date(2026, 9, 24)
    assert component_valid_at(_comp(1, "1", valid=d, invalid=d), d)
    assert not component_valid_at(_comp(1, "1", valid=d + timedelta(days=1)), d)
    assert not component_valid_at(_comp(1, "1", invalid=d - timedelta(days=1)), d)


def test_low_level_codes_chain():
    llc, cycles = compute_low_level_codes({1: {2}, 2: {3}})
    assert llc == {1: 0, 2: 1, 3: 2}
    assert cycles == []


def test_low_level_codes_cycle_detected():
    llc, cycles = compute_low_level_codes({1: {2}, 2: {1}})
    assert cycles, "环路应被识别"


def test_explode_qty_scrap_and_offset():
    parent_start = date(2026, 10, 1)
    reqs = explode(parent_start, Decimal("10"), [_comp(2, "3", scrap="2", offset=2)])
    assert len(reqs) == 1
    assert reqs[0].need_date == date(2026, 9, 29)
    # K3 FScrap 是百分数：2 表示 2%，不是 200%
    assert reqs[0].qty == Decimal("10") * Decimal("3") * Decimal("1.02")


def test_explode_base_qty_divides_standard_qty():
    parent_start = date(2026, 10, 1)
    reqs = explode(parent_start, Decimal("10"), [_comp(2, "3", base="5")])
    assert len(reqs) == 1
    # 标准用量 3 是每 5 个父件用量，10 个父件需要 6
    assert reqs[0].qty == Decimal("6")


def test_explode_validity_filtered_by_child_date():
    parent_start = date(2026, 10, 1)
    comp = _comp(2, "1", offset=5, valid=date(2026, 9, 27))
    # 子件需求日 = 9-26 < 生效日 9-27 → 被过滤
    assert explode(parent_start, Decimal("1"), [comp]) == []
    comp2 = _comp(2, "1", offset=5, valid=date(2026, 9, 26))
    assert len(explode(parent_start, Decimal("1"), [comp2])) == 1


def test_flatten_phantom_penetrates():
    comps = {1: [_comp(2, "2")], 2: [_comp(3, "3")]}
    result = flatten_phantom(
        1, date(2026, 10, 1), Decimal("5"),
        get_components=lambda mid: comps.get(mid, []),
        is_phantom=lambda mid: mid == 2,
    )
    assert len(result) == 1
    assert result[0].material_id == 3
    assert result[0].qty == Decimal("5") * Decimal("2") * Decimal("3")


def test_flatten_phantom_applies_scrap_and_base_qty():
    comps = {1: [_comp(2, "2", scrap="2", base="2")]}
    result = flatten_phantom(
        1, date(2026, 10, 1), Decimal("10"),
        get_components=lambda mid: comps.get(mid, []),
        is_phantom=lambda mid: False,
    )
    assert len(result) == 1
    # 10 × (2 ÷ 2) × 1.02 = 10.2
    assert result[0].qty == Decimal("10.2")
