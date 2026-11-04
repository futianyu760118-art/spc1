"""BOM 公共计算口径单测（无 DB）。"""

from decimal import Decimal

from app.services.common.bom_math import bom_component_qty, scrap_multiplier


def test_scrap_multiplier_treats_k3_value_as_percent():
    assert scrap_multiplier(Decimal("2")) == Decimal("1.02")
    assert scrap_multiplier(Decimal("0.5")) == Decimal("1.005")
    assert scrap_multiplier(None) == Decimal("1")


def test_bom_component_qty_applies_base_qty():
    assert bom_component_qty(
        Decimal("10"), Decimal("3"), Decimal("2"), Decimal("5")
    ) == Decimal("6.12")


def test_bom_component_qty_guards_invalid_base_qty():
    assert bom_component_qty(
        Decimal("10"), Decimal("3"), Decimal("0"), Decimal("0")
    ) == Decimal("30")
