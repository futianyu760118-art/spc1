"""MRP K3 对比判定纯函数单测（无 DB）。"""

from datetime import date, timedelta
from decimal import Decimal

from app.services.mrp.comparison import classify_comparison

_BASE_DATE = date(2026, 9, 30)
_WINDOW = 3
_THRESHOLD = Decimal("5")


def _sug(sid, mid, qty, need):
    return {"id": sid, "material_id": mid, "suggest_qty": Decimal(qty), "need_date": need}


def _k3(qty, need, orders=1):
    return {"qty": Decimal(qty), "need_date": need, "orders": orders}


def test_classify_match():
    counts, rows, k3_only = classify_comparison(
        [_sug(1, 100, "10", _BASE_DATE)],
        {100: _k3("10", _BASE_DATE)},
        _WINDOW,
        _THRESHOLD,
    )
    assert counts == {"match": 1, "diff_qty": 0, "diff_date": 0, "spc_only": 0}
    assert rows == [
        {"suggestion_id": 1, "status": "match", "k3_qty": Decimal("10"), "k3_need_date": _BASE_DATE}
    ]
    assert k3_only == []


def test_classify_diff_qty():
    counts, rows, _ = classify_comparison(
        [_sug(7, 100, "120", _BASE_DATE)],
        {100: _k3("100", _BASE_DATE)},
        _WINDOW,
        _THRESHOLD,
    )
    assert counts["diff_qty"] == 1
    assert rows[0]["status"] == "diff_qty"
    assert rows[0]["k3_qty"] == Decimal("100")


def test_classify_diff_date():
    counts, rows, _ = classify_comparison(
        [_sug(7, 100, "100", _BASE_DATE)],
        {100: _k3("100", _BASE_DATE + timedelta(days=4))},
        _WINDOW,
        _THRESHOLD,
    )
    assert counts["diff_date"] == 1
    assert rows[0]["status"] == "diff_date"
    assert rows[0]["k3_need_date"] == _BASE_DATE + timedelta(days=4)


def test_classify_spc_only():
    counts, rows, k3_only = classify_comparison(
        [_sug(1, 100, "10", _BASE_DATE)],
        {200: _k3("5", _BASE_DATE)},
        _WINDOW,
        _THRESHOLD,
    )
    assert counts == {"match": 0, "diff_qty": 0, "diff_date": 0, "spc_only": 1}
    assert rows[0] == {
        "suggestion_id": 1,
        "status": "spc_only",
        "k3_qty": None,
        "k3_need_date": None,
    }
    assert k3_only[0]["material_id"] == 200
    assert k3_only[0]["qty"] == Decimal("5")


def test_classify_k3_only_lists_unused_groups():
    _, _, k3_only = classify_comparison(
        [_sug(1, 100, "10", _BASE_DATE)],
        {100: _k3("10", _BASE_DATE), 200: _k3("5", _BASE_DATE, orders=2)},
        _WINDOW,
        _THRESHOLD,
    )
    assert [group["material_id"] for group in k3_only] == [200]
    assert k3_only[0]["orders"] == 2


def test_classify_threshold_boundary_inclusive():
    # 差 5/100 = 5% 恰在阈值上 → match
    _, rows, _ = classify_comparison(
        [_sug(1, 100, "95", _BASE_DATE)],
        {100: _k3("100", _BASE_DATE)},
        _WINDOW,
        Decimal("5"),
    )
    assert rows[0]["status"] == "match"
    # 差 6% → diff_qty
    _, rows_over, _ = classify_comparison(
        [_sug(1, 100, "94", _BASE_DATE)],
        {100: _k3("100", _BASE_DATE)},
        _WINDOW,
        Decimal("5"),
    )
    assert rows_over[0]["status"] == "diff_qty"


def test_classify_date_window_boundary_inclusive():
    # 差 3 天 = 窗口上界 → match；4 天 → diff_date
    _, rows, _ = classify_comparison(
        [_sug(1, 100, "10", _BASE_DATE)],
        {100: _k3("10", _BASE_DATE + timedelta(days=3))},
        _WINDOW,
        _THRESHOLD,
    )
    assert rows[0]["status"] == "match"
    _, rows_over, _ = classify_comparison(
        [_sug(1, 100, "10", _BASE_DATE)],
        {100: _k3("10", _BASE_DATE + timedelta(days=4))},
        _WINDOW,
        _THRESHOLD,
    )
    assert rows_over[0]["status"] == "diff_date"


def test_classify_zero_k3_qty_uses_suggestion_base():
    # k3_qty<=0 时以建议量为基数：建议>0 必然超阈值；双方同为 0 视为一致
    _, rows, _ = classify_comparison(
        [_sug(1, 100, "10", _BASE_DATE)],
        {100: _k3("0", _BASE_DATE)},
        _WINDOW,
        _THRESHOLD,
    )
    assert rows[0]["status"] == "diff_qty"
    counts, rows_zero, _ = classify_comparison(
        [_sug(2, 100, "0", _BASE_DATE)],
        {100: _k3("0", _BASE_DATE)},
        _WINDOW,
        _THRESHOLD,
    )
    assert counts["match"] == 1
    assert rows_zero[0]["status"] == "match"


def test_classify_mixed_counts_and_order():
    counts, rows, k3_only = classify_comparison(
        [
            _sug(1, 100, "10", _BASE_DATE),
            _sug(2, 101, "50", _BASE_DATE),
            _sug(3, 102, "10", _BASE_DATE),
            _sug(4, 999, "10", _BASE_DATE),
        ],
        {
            100: _k3("10", _BASE_DATE + timedelta(days=1)),
            101: _k3("10", _BASE_DATE),
            102: _k3("10", _BASE_DATE - timedelta(days=5)),
        },
        _WINDOW,
        _THRESHOLD,
    )
    assert counts == {"match": 1, "diff_qty": 1, "diff_date": 1, "spc_only": 1}
    assert [row["status"] for row in rows] == ["match", "diff_qty", "diff_date", "spc_only"]
    assert k3_only == []
