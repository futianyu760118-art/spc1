"""MRP 替代料纯函数单测（无 DB）。"""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from app.services.mrp.substitute_calc import (
    SuggestionDraft,
    SubstituteRule,
    apply_substitutes,
    build_lendable_balance,
    rule_valid_on,
)

D0 = date(2026, 9, 24)

_BASE_RULE = SubstituteRule(
    id=1,
    main_material_id=10,
    substitute_material_id=20,
    priority=1,
    policy="priority",
    ratio=None,
    substitute_mode="offset",
)


def _d(days: int) -> date:
    return D0 + timedelta(days=days)


def _balance(amount: Decimal) -> "LendableBalance":
    return build_lendable_balance(
        opening=amount,
        supplies=[],
        own_demands=[],
        safety_stock=Decimal("0"),
    )


def _suggestion(suggestion_id: int, material_id: int, qty: Decimal) -> SuggestionDraft:
    return SuggestionDraft(
        suggestion_id=suggestion_id,
        material_id=material_id,
        need_date=D0,
        qty=qty,
    )


def test_rule_valid_on_enabled_window_and_unbounded():
    rule = replace(_BASE_RULE, valid_from=_d(0), valid_to=_d(10))
    assert rule_valid_on(rule, _d(0))
    assert rule_valid_on(rule, _d(10))
    assert not rule_valid_on(rule, _d(-1))
    assert not rule_valid_on(rule, _d(11))
    assert not rule_valid_on(replace(rule, enabled=False), _d(0))
    unbounded = replace(_BASE_RULE, valid_from=None, valid_to=None)
    assert rule_valid_on(unbounded, _d(3650))


def test_build_balance_no_events_keeps_full_lendable_step():
    balance = build_lendable_balance(
        opening=Decimal("100"),
        supplies=[],
        own_demands=[],
        safety_stock=Decimal("20"),
    )
    # 100 − 安全库存 20 = 80，无事件时以 date.min 步进表达，任意需求日可借
    assert balance.steps == [[date.min, Decimal("80")]]
    assert balance.available_until(_d(0)) == Decimal("80")
    assert balance.available_until(_d(-3650)) == Decimal("80")


def test_build_balance_steps_per_date_with_safety_floor():
    balance = build_lendable_balance(
        opening=Decimal("15"),
        supplies=[(_d(5), Decimal("50")), (_d(10), Decimal("10"))],
        own_demands=[(_d(2), Decimal("5"))],
        safety_stock=Decimal("20"),
    )
    # d2 自身需求 −5 后水位低于安全库存 → 0；d5 到货 → 40；d10 → 50（步进记录水位，含下降）
    assert balance.steps == [
        [_d(2), Decimal("0")],
        [_d(5), Decimal("40")],
        [_d(10), Decimal("50")],
    ]
    assert balance.available_until(_d(4)) == Decimal("0")
    assert balance.available_until(_d(5)) == Decimal("40")
    assert balance.available_until(_d(10)) == Decimal("50")


def test_build_balance_clamps_below_safety_stock():
    balance = build_lendable_balance(
        opening=Decimal("15"),
        supplies=[(_d(5), Decimal("3"))],
        own_demands=[],
        safety_stock=Decimal("20"),
    )
    # 15 + 3 − 20 < 0 → 无可借，事件日步进为 0
    assert balance.steps == [[_d(5), Decimal("0")]]
    assert balance.available_until(_d(5)) == Decimal("0")


def test_consume_respects_need_date_and_tracks_lent():
    balance = build_lendable_balance(
        opening=Decimal("0"),
        supplies=[(_d(5), Decimal("30")), (_d(10), Decimal("50"))],
        own_demands=[],
        safety_stock=Decimal("0"),
    )
    # 需求日 d7：只能吃 ≤ d7 的 d5 水位
    assert balance.consume(_d(7), Decimal("10")) == Decimal("10")
    assert balance.available_until(_d(7)) == Decimal("20")
    assert balance.available_until(_d(10)) == Decimal("70")
    # 需求日 d10：水位 80 − 已借 10 = 70，可再借 50
    assert balance.consume(_d(10), Decimal("50")) == Decimal("50")
    assert balance.available_until(_d(10)) == Decimal("20")
    assert balance.total_consumed == Decimal("60")


def test_consume_limited_to_available_and_need_date():
    balance = build_lendable_balance(
        opening=Decimal("0"),
        supplies=[(_d(10), Decimal("50"))],
        own_demands=[],
        safety_stock=Decimal("0"),
    )
    assert balance.consume(_d(5), Decimal("80")) == Decimal("0")
    assert balance.consume(_d(10), Decimal("80")) == Decimal("50")
    assert balance.total_consumed == Decimal("50")


def test_priority_consumes_first_rule_then_next():
    rules = [
        replace(_BASE_RULE, id=1, substitute_material_id=20, priority=1),
        replace(_BASE_RULE, id=2, substitute_material_id=30, priority=2),
    ]
    balances = {20: _balance(Decimal("30")), 30: _balance(Decimal("100"))}
    adjusted, outcome = apply_substitutes(
        suggestions=[_suggestion(0, 10, Decimal("50"))],
        rules=rules,
        balances=balances,
        run_date=D0,
    )
    assert adjusted[0].qty == Decimal("0")
    assert [(o["substitute_material_id"], o["qty"]) for o in outcome.offsets] == [
        (20, Decimal("30")),
        (30, Decimal("20")),
    ]
    assert outcome.replace_targets == {}
    assert balances[20].available_until(D0) == Decimal("0")
    assert balances[30].available_until(D0) == Decimal("80")


def test_ratio_policy_allocates_on_initial_qty():
    rules = [
        replace(_BASE_RULE, id=1, substitute_material_id=20, priority=1, policy="ratio", ratio=Decimal("40")),
        replace(_BASE_RULE, id=2, substitute_material_id=30, priority=2, policy="ratio", ratio=Decimal("60")),
    ]
    balances = {20: _balance(Decimal("100")), 30: _balance(Decimal("100"))}
    adjusted, outcome = apply_substitutes(
        suggestions=[_suggestion(0, 10, Decimal("100"))],
        rules=rules,
        balances=balances,
        run_date=D0,
    )
    # 按原量 100 分摊：40 + 60，余额充足时主料建议清零
    assert [o["qty"] for o in outcome.offsets] == [Decimal("40"), Decimal("60")]
    assert adjusted[0].qty == Decimal("0")


def test_ratio_one_side_short_other_fills_within_gap():
    rules = [
        replace(_BASE_RULE, id=1, substitute_material_id=20, priority=1, policy="ratio", ratio=Decimal("40")),
        replace(_BASE_RULE, id=2, substitute_material_id=30, priority=2, policy="ratio", ratio=Decimal("60")),
    ]
    balances = {20: _balance(Decimal("30")), 30: _balance(Decimal("100"))}
    adjusted, outcome = apply_substitutes(
        suggestions=[_suggestion(0, 10, Decimal("100"))],
        rules=rules,
        balances=balances,
        run_date=D0,
    )
    # 40% 目标 40 但余额仅 30；60% 目标 60 全额满足；合计 90 ≤ 缺口 100，剩余 10 留建议
    assert [o["qty"] for o in outcome.offsets] == [Decimal("30"), Decimal("60")]
    assert adjusted[0].qty == Decimal("10")


def test_lendable_balance_drops_with_own_demand_and_lending():
    balance = build_lendable_balance(
        opening=Decimal("0"),
        supplies=[(_d(10), Decimal("100"))],
        own_demands=[(_d(20), Decimal("80"))],
        safety_stock=Decimal("0"),
    )
    # 先增后降：d10 水位 100，d20 自身需求后水位 20
    assert balance.steps == [[_d(10), Decimal("100")], [_d(20), Decimal("20")]]
    assert balance.available_until(_d(15)) == Decimal("100")
    assert balance.available_until(_d(25)) == Decimal("20")

    rules = [
        replace(_BASE_RULE, id=1, main_material_id=10, substitute_material_id=20),
        replace(_BASE_RULE, id=2, main_material_id=11, substitute_material_id=20),
    ]
    adjusted, outcome = apply_substitutes(
        suggestions=[
            SuggestionDraft(0, 10, _d(15), Decimal("80")),
            SuggestionDraft(1, 11, _d(25), Decimal("50")),
        ],
        rules=rules,
        balances={20: balance},
        run_date=D0,
    )
    # d15 跨主料借出 80 后，d25 水位 20 被已借占用 → 无可借
    assert [o["qty"] for o in outcome.offsets] == [Decimal("80")]
    assert [s.qty for s in adjusted] == [Decimal("0"), Decimal("50")]
    assert balance.available_until(_d(25)) == Decimal("0")


def test_shared_substitute_balance_not_lent_twice():
    rules = [
        replace(_BASE_RULE, id=1, substitute_material_id=20),
        replace(_BASE_RULE, id=2, main_material_id=11, substitute_material_id=20),
    ]
    balances = {20: _balance(Decimal("50"))}
    adjusted, outcome = apply_substitutes(
        suggestions=[
            _suggestion(0, 10, Decimal("40")),
            _suggestion(1, 11, Decimal("40")),
        ],
        rules=rules,
        balances=balances,
        run_date=D0,
    )
    # 同一替代料余额 50 被两条主料建议共享：先借 40，再借 10，不重复借出
    assert [s.qty for s in adjusted] == [Decimal("0"), Decimal("30")]
    assert [o["qty"] for o in outcome.offsets] == [Decimal("40"), Decimal("10")]
    assert balances[20].total_consumed == Decimal("50")
    assert balances[20].available_until(D0) == Decimal("0")


def test_offset_reduces_suggestion_and_reaches_zero():
    rule = replace(_BASE_RULE, id=1, substitute_material_id=20, substitute_mode="replace")
    partial, outcome = apply_substitutes(
        suggestions=[_suggestion(0, 10, Decimal("130"))],
        rules=[rule],
        balances={20: _balance(Decimal("100"))},
        run_date=D0,
    )
    assert partial[0].qty == Decimal("30")
    assert outcome.offsets[0]["qty"] == Decimal("100")
    # 有消费时不触发 replace
    assert outcome.replace_targets == {}

    full, full_outcome = apply_substitutes(
        suggestions=[_suggestion(0, 10, Decimal("100"))],
        rules=[rule],
        balances={20: _balance(Decimal("100"))},
        run_date=D0,
    )
    # 全抵为 0
    assert full[0].qty == Decimal("0")
    assert full_outcome.offsets[0]["qty"] == Decimal("100")
    assert full_outcome.replace_targets == {}


def test_replace_only_when_no_balance_consumed():
    replace_rule = replace(_BASE_RULE, id=1, substitute_material_id=20, substitute_mode="replace")
    # 无余额 → 替换（数量不变）
    adjusted, outcome = apply_substitutes(
        suggestions=[_suggestion(0, 10, Decimal("50"))],
        rules=[replace_rule],
        balances={20: _balance(Decimal("0"))},
        run_date=D0,
    )
    assert adjusted[0].qty == Decimal("50")
    assert outcome.replace_targets == {0: 20}

    # 余额段晚于需求日 → 抵不到 → 替换
    late_balance = build_lendable_balance(
        opening=Decimal("0"),
        supplies=[(_d(10), Decimal("50"))],
        own_demands=[],
        safety_stock=Decimal("0"),
    )
    late_sug, late_outcome = apply_substitutes(
        suggestions=[_suggestion(1, 10, Decimal("50"))],
        rules=[replace_rule],
        balances={20: late_balance},
        run_date=D0,
    )
    assert late_sug[0].qty == Decimal("50")
    assert late_outcome.replace_targets == {1: 20}

    # 有余额消费 → 不替换
    sug, outcome2 = apply_substitutes(
        suggestions=[_suggestion(2, 10, Decimal("50"))],
        rules=[replace_rule],
        balances={20: _balance(Decimal("30"))},
        run_date=D0,
    )
    assert sug[0].qty == Decimal("20")
    assert outcome2.replace_targets == {}

    # offset 规则无余额 → 不替换
    offset_rule = replace(replace_rule, substitute_mode="offset")
    _, offset_outcome = apply_substitutes(
        suggestions=[_suggestion(3, 10, Decimal("50"))],
        rules=[offset_rule],
        balances={20: _balance(Decimal("0"))},
        run_date=D0,
    )
    assert offset_outcome.replace_targets == {}


def test_invalid_rules_ignored_by_apply_substitutes():
    disabled = replace(_BASE_RULE, id=1, substitute_material_id=20, enabled=False, substitute_mode="replace")
    future = replace(_BASE_RULE, id=2, substitute_material_id=30, substitute_mode="replace", valid_from=_d(1))
    expired = replace(_BASE_RULE, id=3, substitute_material_id=40, substitute_mode="replace", valid_to=_d(-1))
    adjusted, outcome = apply_substitutes(
        suggestions=[_suggestion(0, 10, Decimal("50"))],
        rules=[disabled, future, expired],
        balances={
            20: _balance(Decimal("50")),
            30: _balance(Decimal("50")),
            40: _balance(Decimal("50")),
        },
        run_date=D0,
    )
    assert adjusted[0].qty == Decimal("50")
    assert outcome.offsets == []
    assert outcome.replace_targets == {}
