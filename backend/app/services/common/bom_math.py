"""BOM 计算公共口径：损耗率与基础用量。

K3 `FScrap` 以百分数存储（2 表示 2%），同步到 `scm_bom_detail.scrap_rate`
后仍保留原值；所有消费方统一通过本模块转换，避免各自按小数误用。
"""

from decimal import Decimal
from typing import Optional

_ONE = Decimal("1")
_HUNDRED = Decimal("100")


def scrap_multiplier(scrap_rate: Optional[Decimal]) -> Decimal:
    """把 K3 百分数损耗率转换为 `1 + 损耗率` 的乘数。"""
    if scrap_rate is None:
        return _ONE
    return _ONE + Decimal(str(scrap_rate)) / _HUNDRED


def bom_component_qty(
    parent_qty: Decimal,
    standard_qty: Decimal,
    scrap_rate: Optional[Decimal] = None,
    base_qty: Optional[Decimal] = None,
) -> Decimal:
    """按 BOM 基础用量与损耗率计算子件需求。

    公式：父件量 × 标准用量 ÷ 基础用量 × (1 + 损耗率 / 100)
    """
    base = Decimal(str(base_qty)) if base_qty is not None else _ONE
    if base <= 0:
        base = _ONE
    return parent_qty * standard_qty / base * scrap_multiplier(scrap_rate)
