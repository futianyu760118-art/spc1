"""MRP BOM 展开：低位码 + 时间维度（纯函数，便于单测）。"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, Iterable, Optional


@dataclass(frozen=True)
class BomComponent:
    material_id: int
    standard_qty: Decimal
    scrap_rate: Decimal
    lead_offset_days: int
    valid_date: Optional[date]
    invalid_date: Optional[date]


@dataclass(frozen=True)
class ChildRequirement:
    material_id: int
    need_date: date
    qty: Decimal


def component_valid_at(component: BomComponent, ref_date: date) -> bool:
    if component.valid_date is not None and ref_date < component.valid_date:
        return False
    if component.invalid_date is not None and ref_date > component.invalid_date:
        return False
    return True


def compute_low_level_codes(edges: dict[int, set[int]]) -> tuple[dict[int, int], list[int]]:
    """edges: 父物料 → {子物料}。返回 (低层码, 环路物料列表)。"""
    llc: dict[int, int] = {}
    for parent, children in edges.items():
        llc.setdefault(parent, 0)
        for child in children:
            llc.setdefault(child, 0)
    for _ in range(len(llc) + 1):
        changed = False
        for parent, children in edges.items():
            parent_level = llc.get(parent, 0)
            for child in children:
                if llc.get(child, 0) < parent_level + 1:
                    llc[child] = parent_level + 1
                    changed = True
        if not changed:
            return llc, []
    # 未收敛：存在环路，返回所有仍在传播的物料（它们在环上或受环影响）
    cycle_nodes = sorted(n for n, level in llc.items() if level > len(llc))
    return llc, cycle_nodes


def explode(
    parent_start_date: date,
    parent_qty: Decimal,
    components: Iterable[BomComponent],
    ref_date: Optional[date] = None,
) -> list[ChildRequirement]:
    """把父件的计划量展开为直接子件需求（一层）。ref_date 缺省用子件需求日做生效期判断。"""
    result: list[ChildRequirement] = []
    for comp in components:
        child_date = parent_start_date if comp.lead_offset_days == 0 else parent_start_date - _days(comp.lead_offset_days)
        check_date = ref_date or child_date
        if not component_valid_at(comp, check_date):
            continue
        qty = parent_qty * comp.standard_qty * (Decimal("1") + comp.scrap_rate)
        if qty <= 0:
            continue
        result.append(ChildRequirement(comp.material_id, child_date, qty))
    return result


def flatten_phantom(
    material_id: int,
    need_date: date,
    qty: Decimal,
    get_components: Callable[[int], list[BomComponent]],
    is_phantom: Callable[[int], bool],
    depth: int = 0,
) -> list[ChildRequirement]:
    """虚拟件穿透：不生成建议，按层展开到非虚拟件。带 20 层上限防御。"""
    if depth > 20:
        return []
    flattened: list[ChildRequirement] = []
    for comp in get_components(material_id):
        child_date = need_date if comp.lead_offset_days == 0 else need_date - _days(comp.lead_offset_days)
        if not component_valid_at(comp, child_date):
            continue
        child_qty = qty * comp.standard_qty * (Decimal("1") + comp.scrap_rate)
        if child_qty <= 0:
            continue
        if is_phantom(comp.material_id):
            flattened.extend(
                flatten_phantom(comp.material_id, child_date, child_qty, get_components, is_phantom, depth + 1)
            )
        else:
            flattened.append(ChildRequirement(comp.material_id, child_date, child_qty))
    return flattened


def _days(delta: int):
    from datetime import timedelta
    return timedelta(days=delta)
