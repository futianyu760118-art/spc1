"""MRP 替代料计算（纯函数，便于单测）。"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

_ZERO = Decimal("0")


@dataclass(frozen=True)
class SubstituteRule:
    id: int
    main_material_id: int
    substitute_material_id: int
    priority: int
    policy: str            # priority / ratio
    ratio: Optional[Decimal]
    substitute_mode: str   # offset / replace
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    enabled: bool = True


def rule_valid_on(rule: SubstituteRule, ref_date: date) -> bool:
    if not rule.enabled:
        return False
    if rule.valid_from is not None and ref_date < rule.valid_from:
        return False
    if rule.valid_to is not None and ref_date > rule.valid_to:
        return False
    return True


@dataclass
class LendableBalance:
    """替代料可借余额（步进水位 + 已借记录）。

    steps: [[date, lendable_after_date], ...] 按日期升序（含下降步进）
    lent: [[consume_date, qty], ...] 实际借出记录（按需求日约束可用性）
    """

    steps: list[list] = field(default_factory=list)
    lent: list[list] = field(default_factory=list)
    total_consumed: Decimal = _ZERO

    def available_until(self, d: date) -> Decimal:
        base = _ZERO
        for step_date, value in self.steps:
            if step_date <= d:
                base = Decimal(str(value))
            else:
                break
        consumed = sum((Decimal(str(q)) for dd, q in self.lent if dd <= d), _ZERO)
        return max(_ZERO, base - consumed)

    def consume(self, d: date, qty: Decimal) -> Decimal:
        take = min(self.available_until(d), qty)
        if take > 0:
            self.lent.append([d, take])
            self.total_consumed += take
        return take


def build_lendable_balance(
    *,
    opening: Decimal,
    supplies: list[tuple[date, Decimal]],
    own_demands: list[tuple[date, Decimal]],
    safety_stock: Decimal,
) -> LendableBalance:
    events: dict[date, Decimal] = {}
    for d, qty in supplies:
        events[d] = events.get(d, _ZERO) + qty
    for d, qty in own_demands:
        events[d] = events.get(d, _ZERO) - qty
    balance = LendableBalance()
    initial_lendable = opening - safety_stock
    if initial_lendable > 0:
        balance.steps.append([date.min, initial_lendable])
    running = opening
    for d in sorted(events):
        running += events[d]
        balance.steps.append([d, max(_ZERO, running - safety_stock)])
    return balance


@dataclass
class SuggestionDraft:
    """引擎建议 payload 的计算视图（仅替代相关的可变字段）。"""

    suggestion_id: int
    material_id: int
    need_date: date
    qty: Decimal


@dataclass
class SubstitutionOutcome:
    offsets: list[dict] = field(default_factory=list)
    # [{"main_material_id","substitute_material_id","need_date","qty"}]
    replace_targets: dict[int, int] = field(default_factory=dict)
    # suggestion_id -> substitute_material_id


def apply_substitutes(
    *,
    suggestions: list[SuggestionDraft],
    rules: list[SubstituteRule],
    balances: dict[int, LendableBalance],
    run_date: date,
) -> tuple[list[SuggestionDraft], SubstitutionOutcome]:
    """原地/返回调整后的建议；按主料规则消耗替代料余额（offset）或标记替换（replace）。"""
    outcome = SubstitutionOutcome()
    rules_by_main: dict[int, list[SubstituteRule]] = {}
    for rule in rules:
        if rule_valid_on(rule, run_date):
            rules_by_main.setdefault(rule.main_material_id, []).append(rule)
    for main_id in rules_by_main:
        rules_by_main[main_id].sort(key=lambda r: (r.priority, r.id))

    for sug in suggestions:
        main_rules = rules_by_main.get(sug.material_id) or []
        if not main_rules or sug.qty <= 0:
            continue
        initial_qty = sug.qty
        offset_total = _ZERO
        for rule in main_rules:
            if sug.qty <= 0:
                break
            balance = balances.get(rule.substitute_material_id)
            if balance is None:
                continue
            if rule.policy == "ratio" and rule.ratio and rule.ratio > 0:
                target = initial_qty * rule.ratio / Decimal("100")
                target = min(target, sug.qty)
            else:
                target = sug.qty
            consumed = balance.consume(sug.need_date, target)
            if consumed > 0:
                sug.qty -= consumed
                offset_total += consumed
                outcome.offsets.append({
                    "main_material_id": sug.material_id,
                    "substitute_material_id": rule.substitute_material_id,
                    "need_date": sug.need_date,
                    "qty": consumed,
                })
        if offset_total <= 0:
            replace_rule = next((r for r in main_rules if r.substitute_mode == "replace"), None)
            if replace_rule is not None:
                outcome.replace_targets[sug.suggestion_id] = replace_rule.substitute_material_id
    return suggestions, outcome
