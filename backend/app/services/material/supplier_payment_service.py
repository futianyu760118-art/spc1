"""
Supplier Payment Schedule Service.

Data source: aggregates directly from purchase_invoice table.
Filtering logic: users select a target month; the backend calculates
payment_month = invoice_date + payment_term_days, and only includes
invoices whose payment_month matches the selected month, then groups by supplier_code.

Aggregated results (单据有效应付由 _effective_payable 规则确定):
  monthly_due   = SUM(有效应付) for invoices falling in the selected month
  monthly_bill  = SUM(invoice_amount) for invoices falling in the selected month
  total_payable = SUM(remain_payable) - SUM(paid_amount)
                  如果有在途票据，再减去 SUM(在途票据的remain_payable)
"""

import re
from datetime import datetime, timedelta, date as date_type
from decimal import Decimal
from typing import Optional, Tuple, List, Dict, Any

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.purchase_invoice import PurchaseInvoice
from app.schemas.material.schemas import SupplierPaymentSummary
from app.services.common.export_service import GenericExportService, ExportColumn
from app.services.common.sync_filter import get_purchase_invoice_sync_filters


def _to_decimal(v: Any) -> Decimal:
    if v is None:
        return Decimal('0')
    return Decimal(str(v))


def _effective_payable(inv: Dict[str, Any]) -> Decimal:
    """计算票据实际应付（剩余应付）金额。

    规则：
      - paid_amount > 0 → remain_payable - paid_amount
      - paid_amount <= 0 或 null：
          - payment_order_id 存在且 > 0（在途）→ 0（不计入应付）
          - 否则（无付款单）→ remain_payable
    """
    remain = _to_decimal(inv.get('remain_payable'))
    paid_raw = inv.get('paid_amount')
    paid = _to_decimal(paid_raw)
    order_id = inv.get('payment_order_id') or 0
    if paid > 0:
        return remain - paid
    if order_id > 0:
        return Decimal('0')
    return remain


def _default_month() -> str:
    return datetime.now().strftime('%Y-%m')


_PAYMENT_TERM_PATTERNS = [
    r'(\d+)\s*天',       # 30天, 票到30天
    r'(\d+)\s*D',        # 30D
    r'(\d+)\s*days?',    # 30 days
    r'月结\s*(\d+)',     # 月结30
    r'^(\d+)$',          # 纯数字
]


def _extract_days_from_payment_term(payment_term: Optional[str]) -> int:
    """从账期字符串提取天数：支持 '票到30天' / '30天' / '30D' / '30days' / '月结30' / '30'。"""
    if not payment_term:
        return 0
    for pat in _PAYMENT_TERM_PATTERNS:
        m = re.search(pat, payment_term, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                continue
    return 0


def _compute_payment_month(invoice_date, payment_term: Optional[str]) -> Optional[str]:
    """排款月 = 到票日期 + 账期天数，格式 YYYY-MM。"""
    if not invoice_date:
        return None
    days = _extract_days_from_payment_term(payment_term)
    due = invoice_date + timedelta(days=days)
    return due.strftime('%Y-%m')


def _compute_overdue_not_due(invoices: List[Dict[str, Any]]) -> Tuple[Decimal, Decimal]:
    current_month = datetime.now().strftime('%Y-%m')
    overdue = Decimal('0')
    not_due = Decimal('0')
    for inv in invoices:
        inv_date = inv.get('invoice_date')
        # 到期/未到期金额均按票据实际应付（_effective_payable）统计
        remain = _effective_payable(inv)
        if not inv_date:
            not_due += remain
            continue
        if isinstance(inv_date, str):
            try:
                inv_date = datetime.strptime(inv_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                not_due += remain
                continue
        payment_term = inv.get('payment_term')
        pm = _compute_payment_month(inv_date, payment_term)
        if pm and pm < current_month:
            overdue += remain
        else:
            not_due += remain
    return overdue, not_due


def _compute_overdue_by_month(invoices: List[Dict[str, Any]]) -> Tuple[Decimal, List[Dict[str, Any]]]:
    """按排款月分组计算已到期未付金额（口径与汇总「到期未付」一致）。

    返回 (合计金额, [{'month': 'YYYY-MM', 'amount': Decimal}, ...])，月份升序。
    """
    current_month = datetime.now().strftime('%Y-%m')
    month_map: Dict[str, Decimal] = {}
    for inv in invoices:
        inv_date = inv.get('invoice_date')
        if not inv_date:
            continue
        pm = _compute_payment_month(inv_date, inv.get('payment_term'))
        if not pm or pm >= current_month:
            continue
        remain = _effective_payable(inv)
        if remain > 0:
            month_map[pm] = month_map.get(pm, Decimal('0')) + remain
    total = sum(month_map.values(), Decimal('0'))
    return total, [{'month': m, 'amount': month_map[m]} for m in sorted(month_map)]


def _attach_overdue(
    items: List[Dict[str, Any]],
    all_invoices_map: Dict[str, List[Dict[str, Any]]],
) -> None:
    """为每个聚合行附上 overdue_total 与 overdue_by_month。"""
    for it in items:
        total, month_items = _compute_overdue_by_month(all_invoices_map.get(it['supplier_code'], []))
        it['overdue_total'] = total
        it['overdue_by_month'] = month_items


SORT_LABELS = {
    'supplier_code', 'supplier_name', 'invoice_date',
    'payment_term', 'payment_method', 'total_payable', 'monthly_due', 'monthly_bill', 'payment_month',
    'overdue_total',
}


def _resolve_month(schedule_month: Optional[str], payment_month: Optional[str]) -> str:
    """统一为单一目标月份（YYYY-MM）。payment_month 优先，其次 schedule_month，最后当前月。"""
    return payment_month or schedule_month or _default_month()


def _month_range(month: str) -> Tuple[date_type, date_type]:
    """返回月份的 (月初, 下月初) 日期。"""
    start = datetime.strptime(month, '%Y-%m').date()
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _not_paid_clause():
    """在途付款单过滤条件：排除 (paid_amount<=0/null 且 payment_order_id 存在且非0) 的票据。

    满足该条件的票据已生成付款单但未实际付款（在途），不参与统计与查询。
    返回的是「应统计」条件（取反），用于 WHERE 子句保留待统计票据。
    """
    paid_c = PurchaseInvoice.paid_amount
    order_c = PurchaseInvoice.payment_order_id
    return ~and_(
        (paid_c.is_(None) | (paid_c <= 0)),
        order_c.isnot(None),
        order_c != 0,
    )


async def _fetch_filtered_invoices(
    db: AsyncSession,
    target_month: str,
    supplier_name: Optional[str],
    exact_supplier_name: bool = False,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
    sync_filters: Optional[list] = None,
) -> List[Dict[str, Any]]:
    """查出可能落在 target_month 排款月的发票明细，Python 层精筛。"""
    month_start, month_end = _month_range(target_month)
    # 粗筛：invoice_date 最多提前 180 天（覆盖 0~180 天账期）
    coarse_start = month_start - timedelta(days=180)

    # 如果指定了到票日期范围，使用指定的范围
    if invoice_date_start:
        coarse_start = datetime.strptime(invoice_date_start, '%Y-%m-%d').date()
    if invoice_date_end:
        month_end = datetime.strptime(invoice_date_end, '%Y-%m-%d').date() + timedelta(days=1)

    stmt = select(
        PurchaseInvoice.invoice_no,
        PurchaseInvoice.line_no,
        PurchaseInvoice.supplier_code,
        PurchaseInvoice.supplier_name,
        PurchaseInvoice.invoice_date,
        PurchaseInvoice.payment_term,
        PurchaseInvoice.settlement_method,
        PurchaseInvoice.invoice_amount,
        PurchaseInvoice.remain_payable,
        PurchaseInvoice.payment_apply_amount,
        PurchaseInvoice.paid_amount,
        PurchaseInvoice.payment_order_id,
    ).where(
        PurchaseInvoice.invoice_date >= coarse_start,
        PurchaseInvoice.invoice_date < month_end,
        _not_paid_clause(),
    )

    if sync_filters:
        stmt = stmt.where(*sync_filters)

    if supplier_name:
        if exact_supplier_name:
            stmt = stmt.where(PurchaseInvoice.supplier_name == supplier_name)
        else:
            stmt = stmt.where(PurchaseInvoice.supplier_name.ilike(f'%{supplier_name}%'))

    result = await db.execute(stmt)
    rows = result.mappings().all()

    # 精筛：只保留排款月 == target_month 的发票（如果未指定到票日期范围）
    # 如果指定了到票日期范围，则跳过排款月筛选
    filtered: List[Dict[str, Any]] = []
    for r in rows:
        if invoice_date_start or invoice_date_end:
            # 如果指定了到票日期范围，直接包含所有发票
            filtered.append(dict(r))
        else:
            # 否则按排款月筛选
            pay_month = _compute_payment_month(r['invoice_date'], r['payment_term'])
            if pay_month == target_month:
                filtered.append(dict(r))

    return filtered


def _aggregate_invoices(
    filtered: List[Dict[str, Any]],
    target_month: str,
) -> List[Dict[str, Any]]:
    """按 supplier_code 聚合已筛选的发票明细。

    注意：按排款月筛选时，同一供应商的多张发票到票日期通常各不相同（覆盖整月范围），
    因此汇总行不显示单一到票日期和账期，用户通过展开明细查看。
    """
    groups: Dict[str, Dict[str, Any]] = {}

    for r in filtered:
        code = r['supplier_code'] or ''
        if code not in groups:
            groups[code] = {
                'supplier_code': code,
                'supplier_name': r['supplier_name'],
                'invoice_date': None,
                'payment_term': None,
                'payment_method': r['settlement_method'],
                'monthly_due': Decimal('0'),
                'monthly_bill': Decimal('0'),
                'payment_month': target_month,
                'schedule_month': target_month,
                'invoices': [],
            }
        groups[code]['monthly_due'] += _effective_payable(r)
        groups[code]['monthly_bill'] += (r['invoice_amount'] if r['invoice_amount'] is not None else Decimal('0'))
        # 收集发票明细
        inv_date = r['invoice_date']
        groups[code]['invoices'].append({
            'invoice_no': r['invoice_no'] or '',
            'line_no': r['line_no'] or '',
            'invoice_date': inv_date.isoformat() if inv_date else None,
            'payment_term': r['payment_term'] or '',
            'settlement_method': r['settlement_method'] or '',
            'invoice_amount': float(r['invoice_amount'].quantize(Decimal('0.01'))) if r['invoice_amount'] is not None else 0.0,
            'remain_payable': float(r['remain_payable'].quantize(Decimal('0.01'))) if r['remain_payable'] is not None else 0.0,
            'payment_apply_amount': float(r['payment_apply_amount'].quantize(Decimal('0.01'))) if r['payment_apply_amount'] is not None else 0.0,
            'paid_amount': float(r['paid_amount'].quantize(Decimal('0.01'))) if r['paid_amount'] is not None else 0.0,
            'payment_order_id': r.get('payment_order_id'),
        })

    return list(groups.values())


async def _get_all_suppliers_with_invoices(
    db: AsyncSession,
    supplier_name: Optional[str] = None,
    exact_supplier_name: bool = False,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
    sync_filters: Optional[list] = None,
) -> List[Dict[str, Any]]:
    """获取所有有发票记录的供应商（不限制排款月）。"""
    stmt = select(
        PurchaseInvoice.supplier_code,
        PurchaseInvoice.supplier_name,
        func.max(PurchaseInvoice.settlement_method).label('payment_method'),
    ).group_by(
        PurchaseInvoice.supplier_code,
        PurchaseInvoice.supplier_name,
    )
    stmt = stmt.where(_not_paid_clause())

    if sync_filters:
        stmt = stmt.where(*sync_filters)

    if supplier_name:
        if exact_supplier_name:
            stmt = stmt.where(PurchaseInvoice.supplier_name == supplier_name)
        else:
            stmt = stmt.where(PurchaseInvoice.supplier_name.ilike(f'%{supplier_name}%'))

    if invoice_date_start:
        stmt = stmt.where(PurchaseInvoice.invoice_date >= datetime.strptime(invoice_date_start, '%Y-%m-%d').date())
    if invoice_date_end:
        stmt = stmt.where(PurchaseInvoice.invoice_date <= datetime.strptime(invoice_date_end, '%Y-%m-%d').date())

    result = await db.execute(stmt)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


async def _get_supplier_all_invoices(
    db: AsyncSession,
    supplier_codes: List[str],
    supplier_name: Optional[str] = None,
    exact_supplier_name: bool = False,
    sync_filters: Optional[list] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """获取指定供应商的全部发票明细。"""
    if not supplier_codes:
        return {}

    stmt = select(
        PurchaseInvoice.invoice_no,
        PurchaseInvoice.line_no,
        PurchaseInvoice.supplier_code,
        PurchaseInvoice.invoice_date,
        PurchaseInvoice.payment_term,
        PurchaseInvoice.settlement_method,
        PurchaseInvoice.invoice_amount,
        PurchaseInvoice.remain_payable,
        PurchaseInvoice.payment_apply_amount,
        PurchaseInvoice.paid_amount,
        PurchaseInvoice.payment_order_id,
    ).where(
        PurchaseInvoice.supplier_code.in_(supplier_codes),
        _not_paid_clause(),
    )

    if sync_filters:
        stmt = stmt.where(*sync_filters)

    if supplier_name:
        if exact_supplier_name:
            stmt = stmt.where(PurchaseInvoice.supplier_name == supplier_name)
        else:
            stmt = stmt.where(PurchaseInvoice.supplier_name.ilike(f'%{supplier_name}%'))

    result = await db.execute(stmt)
    rows = result.mappings().all()

    invoice_map: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        code = r['supplier_code']
        if code not in invoice_map:
            invoice_map[code] = []
        invoice_map[code].append({
            'invoice_no': r['invoice_no'] or '',
            'line_no': r['line_no'] or '',
            'invoice_date': r['invoice_date'],
            'payment_term': r['payment_term'] or '',
            'settlement_method': r['settlement_method'] or '',
            'invoice_amount': float(r['invoice_amount'].quantize(Decimal('0.01'))) if r['invoice_amount'] is not None else 0.0,
            'remain_payable': float(r['remain_payable'].quantize(Decimal('0.01'))) if r['remain_payable'] is not None else 0.0,
            'payment_apply_amount': float(r['payment_apply_amount'].quantize(Decimal('0.01'))) if r['payment_apply_amount'] is not None else 0.0,
            'paid_amount': float(r['paid_amount'].quantize(Decimal('0.01'))) if r['paid_amount'] is not None else 0.0,
            'payment_order_id': r.get('payment_order_id'),
        })

    return invoice_map


async def _fill_total_payable(
    db: AsyncSession,
    items: List[Dict[str, Any]],
    supplier_name: Optional[str],
    exact_supplier_name: bool = False,
    sync_filters: Optional[list] = None,
) -> None:
    """回填每个供应商的总应付金额（按票据实际应付规则汇总，不限月份）。

    计算逻辑：
      第一步：总应付 = SUM(remain_payable) - SUM(paid_amount)
      第二步：如果有在途票据（paid_amount<=0/null 且 payment_order_id > 0），
              总应付 = 总应付 - SUM(在途票据的remain_payable)
    """
    if not items:
        return

    codes = [it['supplier_code'] for it in items]
    # 第一步：所有票据的 SUM(remain_payable) - SUM(paid_amount)
    remain_sum = func.coalesce(func.sum(PurchaseInvoice.remain_payable), 0)
    paid_sum = func.coalesce(func.sum(PurchaseInvoice.paid_amount), 0)
    # 第二步：在途票据的 remain_payable 总和
    in_transit_clause = and_(
        (PurchaseInvoice.paid_amount.is_(None) | (PurchaseInvoice.paid_amount <= 0)),
        PurchaseInvoice.payment_order_id.isnot(None),
        PurchaseInvoice.payment_order_id != 0,
    )
    in_transit_remain_sum = func.coalesce(
        func.sum(case((in_transit_clause, PurchaseInvoice.remain_payable), else_=0)),
        0,
    )
    stmt = (
        select(
            PurchaseInvoice.supplier_code.label('supplier_code'),
            ((remain_sum - paid_sum) - in_transit_remain_sum).label('total_payable'),
        )
        .where(PurchaseInvoice.supplier_code.in_(codes))
        .group_by(PurchaseInvoice.supplier_code)
    )
    if sync_filters:
        stmt = stmt.where(*sync_filters)
    if supplier_name:
        if exact_supplier_name:
            stmt = stmt.where(PurchaseInvoice.supplier_name == supplier_name)
        else:
            stmt = stmt.where(PurchaseInvoice.supplier_name.ilike(f'%{supplier_name}%'))

    result = await db.execute(stmt)
    total_map: Dict[str, Decimal] = {}
    for r in result.mappings().all():
        total_map[r['supplier_code']] = (r['total_payable'] if r['total_payable'] is not None else Decimal('0'))

    for it in items:
        it['total_payable'] = total_map.get(it['supplier_code'], Decimal('0'))


def _format_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """格式化单条聚合结果，确保日期/数值格式正确。"""
    invoice_date = item.get('invoice_date')
    return {
        'supplier_code': item['supplier_code'] or '',
        'supplier_name': item['supplier_name'],
        'invoice_date': invoice_date.isoformat() if invoice_date else None,
        'payment_term': item['payment_term'],
        'payment_method': item['payment_method'],
        'total_payable': float(item.get('total_payable', Decimal('0')).quantize(Decimal('0.01'))),
        'monthly_due': float(item.get('monthly_due', Decimal('0')).quantize(Decimal('0.01'))),
        'monthly_bill': float(item.get('monthly_bill', Decimal('0')).quantize(Decimal('0.01'))),
        'payment_month': item.get('payment_month'),
        'schedule_month': item.get('schedule_month'),
        'invoices': item.get('invoices', []),
        'overdue_total': float(item.get('overdue_total', Decimal('0')).quantize(Decimal('0.01'))),
        'overdue_by_month': [
            {'month': m['month'], 'amount': float(m['amount'].quantize(Decimal('0.01')))}
            for m in item.get('overdue_by_month', [])
        ],
    }


async def get_supplier_payment_list(
    db: AsyncSession,
    schedule_month: Optional[str] = None,
    supplier_name: Optional[str] = None,
    exact_supplier_name: bool = False,
    payment_month: Optional[str] = None,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    target_month = _resolve_month(schedule_month, payment_month)

    # 获取采购开票同步延迟过滤条件
    sync_filters = await get_purchase_invoice_sync_filters(db)

    # 获取所有有发票记录的供应商（不限制排款月）
    all_suppliers = await _get_all_suppliers_with_invoices(db, supplier_name, exact_supplier_name, invoice_date_start, invoice_date_end, sync_filters)

    # 获取当前排款月的发票数据
    filtered = await _fetch_filtered_invoices(db, target_month, supplier_name, exact_supplier_name, invoice_date_start, invoice_date_end, sync_filters)
    monthly_items = _aggregate_invoices(filtered, target_month)

    # 创建月到期应付金额映射
    monthly_map = {it['supplier_code']: it for it in monthly_items}

    # 获取所有供应商的全部发票明细（用于非当月供应商的行明细与已到期未付计算）
    all_codes = [s['supplier_code'] for s in all_suppliers]
    all_invoices_map = await _get_supplier_all_invoices(db, all_codes, supplier_name, exact_supplier_name, sync_filters)

    # 合并数据：所有供应商都要显示，月到期应付金额从映射中获取
    items = []
    for supplier in all_suppliers:
        code = supplier['supplier_code']
        if code in monthly_map:
            items.append(monthly_map[code])
        else:
            # 不在当前排款月的供应商，月到期应付金额为0，到票日期和账期不显示，但显示全部发票
            all_invoices = all_invoices_map.get(code, [])
            invoice_list = []
            for inv in all_invoices:
                inv_date = inv['invoice_date']
                invoice_list.append({
                    'invoice_no': inv['invoice_no'],
                    'line_no': inv['line_no'],
                    'invoice_date': inv_date.isoformat() if inv_date else None,
                    'payment_term': inv['payment_term'],
                    'settlement_method': inv['settlement_method'],
                    'invoice_amount': inv['invoice_amount'],
                    'remain_payable': inv['remain_payable'],
                    'payment_apply_amount': inv.get('payment_apply_amount', 0),
                    'paid_amount': inv.get('paid_amount', 0),
                    'payment_order_id': inv.get('payment_order_id'),
                })

            items.append({
                'supplier_code': code,
                'supplier_name': supplier['supplier_name'],
                'invoice_date': None,
                'payment_term': None,
                'payment_method': supplier['payment_method'],
                'monthly_due': Decimal('0'),
                'monthly_bill': Decimal('0'),
                'payment_month': target_month,
                'schedule_month': target_month,
                'invoices': invoice_list,
            })

    # 回填总应付金额
    await _fill_total_payable(db, items, supplier_name, exact_supplier_name, sync_filters)

    # 附上已到期未付合计与月度明细
    _attach_overdue(items, all_invoices_map)

    items = [_format_item(it) for it in items]

    # 排序
    if sort_by and sort_by in SORT_LABELS:
        reverse = sort_order == 'desc'
        items.sort(key=lambda x: (x.get(sort_by) is None, x.get(sort_by)), reverse=reverse)
    else:
        items.sort(key=lambda x: x['supplier_code'])

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total


async def get_supplier_payment_summary(
    db: AsyncSession,
    schedule_month: Optional[str] = None,
    supplier_name: Optional[str] = None,
    exact_supplier_name: bool = False,
    payment_month: Optional[str] = None,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
) -> SupplierPaymentSummary:
    target_month = _resolve_month(schedule_month, payment_month)

    # 获取所有有发票记录的供应商（不限制排款月）
    all_suppliers = await _get_all_suppliers_with_invoices(db, supplier_name, exact_supplier_name, invoice_date_start, invoice_date_end)

    # 获取当前排款月的发票数据
    filtered = await _fetch_filtered_invoices(db, target_month, supplier_name, exact_supplier_name, invoice_date_start, invoice_date_end)
    monthly_items = _aggregate_invoices(filtered, target_month)

    # 创建月到期应付金额映射
    monthly_map = {it['supplier_code']: it for it in monthly_items}

    # 获取不在当前排款月的供应商的全部发票明细
    not_in_month_codes = [s['supplier_code'] for s in all_suppliers if s['supplier_code'] not in monthly_map]
    all_invoices_map = await _get_supplier_all_invoices(db, not_in_month_codes, supplier_name, exact_supplier_name)

    # 合并数据：所有供应商都要显示，月到期应付金额从映射中获取
    items = []
    all_invoices_for_overdue: List[Dict[str, Any]] = []
    for supplier in all_suppliers:
        code = supplier['supplier_code']
        if code in monthly_map:
            items.append(monthly_map[code])
            all_invoices_for_overdue.extend(monthly_map[code].get('invoices', []))
        else:
            # 不在当前排款月的供应商，月到期应付金额为0，到票日期和账期不显示，但显示全部发票
            all_invoices = all_invoices_map.get(code, [])
            invoice_list = []
            for inv in all_invoices:
                inv_date = inv['invoice_date']
                invoice_list.append({
                    'invoice_no': inv['invoice_no'],
                    'line_no': inv['line_no'],
                    'invoice_date': inv_date.isoformat() if inv_date else None,
                    'payment_term': inv['payment_term'],
                    'settlement_method': inv['settlement_method'],
                    'invoice_amount': inv['invoice_amount'],
                    'remain_payable': inv['remain_payable'],
                    'payment_apply_amount': inv.get('payment_apply_amount', 0),
                    'paid_amount': inv.get('paid_amount', 0),
                    'payment_order_id': inv.get('payment_order_id'),
                })

            items.append({
                'supplier_code': code,
                'supplier_name': supplier['supplier_name'],
                'invoice_date': None,
                'payment_term': None,
                'payment_method': supplier['payment_method'],
                'monthly_due': Decimal('0'),
                'monthly_bill': Decimal('0'),
                'payment_month': target_month,
                'schedule_month': target_month,
                'invoices': invoice_list,
            })
            all_invoices_for_overdue.extend(invoice_list)

    # 回填总应付金额
    await _fill_total_payable(db, items, supplier_name, exact_supplier_name)

    total_payable = Decimal('0')
    total_monthly_due = Decimal('0')
    supplier_codes = set()
    for it in items:
        if it['supplier_code']:
            supplier_codes.add(it['supplier_code'])
        total_payable += it.get('total_payable', Decimal('0'))
        total_monthly_due += it.get('monthly_due', Decimal('0'))

    overdue_amount, not_due_amount = _compute_overdue_not_due(all_invoices_for_overdue)

    return SupplierPaymentSummary(
        total_payable=float(total_payable.quantize(Decimal('0.01'))),
        total_monthly_due=float(total_monthly_due.quantize(Decimal('0.01'))),
        supplier_count=len(supplier_codes),
        overdue_amount=float(overdue_amount.quantize(Decimal('0.01'))),
        not_due_amount=float(not_due_amount.quantize(Decimal('0.01'))),
    )


EXPORT_COLUMNS = [
    ExportColumn('supplier_code', '供应商编码', 16),
    ExportColumn('supplier_name', '供应商', 24),
    ExportColumn('invoice_date', '到票日期', 12),
    ExportColumn('payment_term', '账期', 10),
    ExportColumn('payment_method', '付款方式', 12),
    ExportColumn('payment_month', '排款月', 12),
    ExportColumn('total_payable', '总应付金额', 14),
    ExportColumn('monthly_due', '月到期应付金额', 16),
    ExportColumn('overdue_total', '实际到期未付', 14),
]


async def get_supplier_payment_export(
    db: AsyncSession,
    format: str = 'xlsx',
    schedule_month: Optional[str] = None,
    supplier_name: Optional[str] = None,
    exact_supplier_name: bool = False,
    payment_month: Optional[str] = None,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Tuple[Any, str, str]:
    """导出供应商付款排程（不分页），返回 (BytesIO, media_type, filename)。"""
    target_month = _resolve_month(schedule_month, payment_month)

    # 获取采购开票同步延迟过滤条件
    sync_filters = await get_purchase_invoice_sync_filters(db)

    # 获取所有有发票记录的供应商（不限制排款月）
    all_suppliers = await _get_all_suppliers_with_invoices(db, supplier_name, exact_supplier_name, invoice_date_start, invoice_date_end, sync_filters)

    # 获取当前排款月的发票数据
    filtered = await _fetch_filtered_invoices(db, target_month, supplier_name, exact_supplier_name, invoice_date_start, invoice_date_end, sync_filters)
    monthly_items = _aggregate_invoices(filtered, target_month)

    # 创建月到期应付金额映射
    monthly_map = {it['supplier_code']: it for it in monthly_items}

    # 获取所有供应商的全部发票明细（用于非当月供应商的行明细与已到期未付计算）
    all_codes = [s['supplier_code'] for s in all_suppliers]
    all_invoices_map = await _get_supplier_all_invoices(db, all_codes, supplier_name, exact_supplier_name, sync_filters)

    # 合并数据：所有供应商都要显示，月到期应付金额从映射中获取
    items = []
    for supplier in all_suppliers:
        code = supplier['supplier_code']
        if code in monthly_map:
            items.append(monthly_map[code])
        else:
            # 不在当前排款月的供应商，月到期应付金额为0，到票日期和账期不显示，但显示全部发票
            all_invoices = all_invoices_map.get(code, [])
            invoice_list = []
            for inv in all_invoices:
                inv_date = inv['invoice_date']
                invoice_list.append({
                    'invoice_no': inv['invoice_no'],
                    'line_no': inv['line_no'],
                    'invoice_date': inv_date.isoformat() if inv_date else None,
                    'payment_term': inv['payment_term'],
                    'settlement_method': inv['settlement_method'],
                    'invoice_amount': inv['invoice_amount'],
                    'remain_payable': inv['remain_payable'],
                    'payment_apply_amount': inv.get('payment_apply_amount', 0),
                    'paid_amount': inv.get('paid_amount', 0),
                    'payment_order_id': inv.get('payment_order_id'),
                })

            items.append({
                'supplier_code': code,
                'supplier_name': supplier['supplier_name'],
                'invoice_date': None,
                'payment_term': None,
                'payment_method': supplier['payment_method'],
                'monthly_due': Decimal('0'),
                'monthly_bill': Decimal('0'),
                'payment_month': target_month,
                'schedule_month': target_month,
                'invoices': invoice_list,
            })

    # 回填总应付金额
    await _fill_total_payable(db, items, supplier_name, exact_supplier_name, sync_filters)

    # 附上已到期未付合计与月度明细
    _attach_overdue(items, all_invoices_map)

    items = [_format_item(it) for it in items]

    # 排序
    if sort_by and sort_by in SORT_LABELS:
        reverse = sort_order == 'desc'
        items.sort(key=lambda x: (x.get(sort_by) is None, x.get(sort_by)), reverse=reverse)
    else:
        items.sort(key=lambda x: x['supplier_code'])

    export_rows = []
    for it in items:
        export_rows.append({
            'supplier_code': it['supplier_code'] or '',
            'supplier_name': it['supplier_name'] or '',
            'invoice_date': it['invoice_date'] or '',
            'payment_term': it['payment_term'] or '',
            'payment_method': it['payment_method'] or '',
            'payment_month': it.get('payment_month') or '',
            'total_payable': it.get('total_payable', 0),
            'monthly_due': it.get('monthly_due', 0),
            'overdue_total': it.get('overdue_total', 0),
        })

    svc = GenericExportService(EXPORT_COLUMNS, export_rows, sheet_name='供应商付款排程')

    if format == 'csv':
        output = svc.to_csv()
        return output, 'text/csv; charset=utf-8', 'supplier_payment.csv'
    else:
        output = svc.to_xlsx()
        return output, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'supplier_payment.xlsx'