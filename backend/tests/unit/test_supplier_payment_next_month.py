"""下月应付金额计算单测（无 DB）。"""

from datetime import date
from decimal import Decimal

from app.services.material.supplier_payment_service import _compute_next_month_due


def _inv(invoice_date=None, term=None, remain='100', paid=0, order_id=None, apply_date=None):
    return {
        'invoice_date': invoice_date,
        'payment_term': term,
        'remain_payable': Decimal(remain),
        'paid_amount': Decimal(paid),
        'payment_order_id': order_id,
        'payment_apply_date': apply_date,
    }


def test_progress_month_next_month():
    # 进度月 2026-08；10月有应付、11月也有 → 取 10月
    invs = [
        _inv(date(2026, 9, 1), '30天', apply_date=date(2026, 8, 10)),   # 排款月 2026-10
        _inv(date(2026, 10, 20), '30天', apply_date=date(2026, 8, 5)),  # 排款月 2026-11
    ]
    assert _compute_next_month_due(invs) == ('2026-10', Decimal('100'))


def test_skip_empty_month():
    # 进度月 2026-07；8月已全付（有效应付0），9月有应付 → 9月
    invs = [
        _inv(date(2026, 8, 1), '30天', remain='100', paid=100, apply_date=date(2026, 7, 20)),  # 排款月 2026-08 全付
        _inv(date(2026, 8, 20), '30天', apply_date=date(2026, 7, 20)),  # 排款月 2026-09
    ]
    assert _compute_next_month_due(invs) == ('2026-09', Decimal('100'))


def test_no_apply_falls_back_earliest():
    # 无付款申请记录 → 最早应付月
    invs = [
        _inv(date(2026, 5, 1), '30天'),  # 排款月 2026-05
        _inv(date(2026, 4, 1), '30天'),  # 排款月 2026-05
    ]
    assert _compute_next_month_due(invs) == ('2026-05', Decimal('200'))


def test_all_paid_after_progress_returns_none():
    # 进度月之后全空 → None
    invs = [_inv(date(2026, 7, 1), '30天', remain='100', paid=100, apply_date=date(2026, 8, 1))]
    assert _compute_next_month_due(invs) == (None, None)


def test_in_transit_not_counted():
    # 在途票据（payment_order_id>0 未付）有效应付为0，跳过该月
    invs = [
        _inv(date(2026, 9, 1), '30天', order_id=5, apply_date=date(2026, 7, 1)),   # 排款月 2026-10，在途不计
        _inv(date(2026, 10, 20), '30天', apply_date=date(2026, 7, 1)),  # 排款月 2026-11
    ]
    assert _compute_next_month_due(invs) == ('2026-11', Decimal('100'))


def test_no_invoice_date_skipped():
    invs = [_inv(None, '30天')]
    assert _compute_next_month_due(invs) == (None, None)
