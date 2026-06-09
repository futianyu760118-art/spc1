"""物料齐套中心 — 供应商付款排程服务

数据来源：直接基于 purchase_invoice 表聚合。
筛选规则：用户选择排款月，后端按 invoice_date + 账期天数 计算排款月，
         只保留排款月等于所选月份的发票，再按 supplier_code 聚合。
聚合结果：
  monthly_due   = 排款月在所选月份的发票 SUM(remain_payable)
  monthly_bill  = 排款月在所选月份的发票 SUM(invoice_amount)
  total_payable = 该供应商所有发票 SUM(remain_payable)
"""

import re
from datetime import datetime, timedelta, date as date_type
from decimal import Decimal
from typing import Optional, Tuple, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.purchase_invoice import PurchaseInvoice
from app.schemas.material.schemas import SupplierPaymentSummary
from app.services.common.export_service import GenericExportService, ExportColumn


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


SORT_LABELS = {
    'supplier_code', 'supplier_name', 'invoice_date',
    'payment_term', 'payment_method', 'total_payable', 'monthly_due', 'monthly_bill',
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


async def _fetch_filtered_invoices(
    db: AsyncSession,
    target_month: str,
    supplier_name: Optional[str],
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
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
    ).where(
        PurchaseInvoice.invoice_date >= coarse_start,
        PurchaseInvoice.invoice_date < month_end,
    )

    if supplier_name:
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
        groups[code]['monthly_due'] += (r['remain_payable'] if r['remain_payable'] is not None else Decimal('0'))
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
        })

    return list(groups.values())


async def _get_all_suppliers_with_invoices(
    db: AsyncSession,
    supplier_name: Optional[str] = None,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
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

    if supplier_name:
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
    ).where(PurchaseInvoice.supplier_code.in_(supplier_codes))

    if supplier_name:
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
        })

    return invoice_map


async def _fill_total_payable(
    db: AsyncSession,
    items: List[Dict[str, Any]],
    supplier_name: Optional[str],
) -> None:
    """回填每个供应商的总应付金额（全量 remain_payable，不限月份）。"""
    if not items:
        return

    codes = [it['supplier_code'] for it in items]
    stmt = (
        select(
            PurchaseInvoice.supplier_code.label('supplier_code'),
            func.sum(PurchaseInvoice.remain_payable).label('total_payable'),
        )
        .where(PurchaseInvoice.supplier_code.in_(codes))
        .group_by(PurchaseInvoice.supplier_code)
    )
    if supplier_name:
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
    }


async def get_supplier_payment_list(
    db: AsyncSession,
    schedule_month: Optional[str] = None,
    supplier_name: Optional[str] = None,
    payment_month: Optional[str] = None,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    target_month = _resolve_month(schedule_month, payment_month)

    # 获取所有有发票记录的供应商（不限制排款月）
    all_suppliers = await _get_all_suppliers_with_invoices(db, supplier_name, invoice_date_start, invoice_date_end)

    # 获取当前排款月的发票数据
    filtered = await _fetch_filtered_invoices(db, target_month, supplier_name, invoice_date_start, invoice_date_end)
    monthly_items = _aggregate_invoices(filtered, target_month)

    # 创建月到期应付金额映射
    monthly_map = {it['supplier_code']: it for it in monthly_items}

    # 获取不在当前排款月的供应商的全部发票明细
    not_in_month_codes = [s['supplier_code'] for s in all_suppliers if s['supplier_code'] not in monthly_map]
    all_invoices_map = await _get_supplier_all_invoices(db, not_in_month_codes, supplier_name)

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
    await _fill_total_payable(db, items, supplier_name)

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
    payment_month: Optional[str] = None,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
) -> SupplierPaymentSummary:
    target_month = _resolve_month(schedule_month, payment_month)

    # 获取所有有发票记录的供应商（不限制排款月）
    all_suppliers = await _get_all_suppliers_with_invoices(db, supplier_name, invoice_date_start, invoice_date_end)

    # 获取当前排款月的发票数据
    filtered = await _fetch_filtered_invoices(db, target_month, supplier_name, invoice_date_start, invoice_date_end)
    monthly_items = _aggregate_invoices(filtered, target_month)

    # 创建月到期应付金额映射
    monthly_map = {it['supplier_code']: it for it in monthly_items}

    # 获取不在当前排款月的供应商的全部发票明细
    not_in_month_codes = [s['supplier_code'] for s in all_suppliers if s['supplier_code'] not in monthly_map]
    all_invoices_map = await _get_supplier_all_invoices(db, not_in_month_codes, supplier_name)

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
    await _fill_total_payable(db, items, supplier_name)

    total_payable = Decimal('0')
    total_monthly_due = Decimal('0')
    supplier_codes = set()
    for it in items:
        if it['supplier_code']:
            supplier_codes.add(it['supplier_code'])
        total_payable += it.get('total_payable', Decimal('0'))
        total_monthly_due += it.get('monthly_due', Decimal('0'))

    return SupplierPaymentSummary(
        total_payable=float(total_payable.quantize(Decimal('0.01'))),
        total_monthly_due=float(total_monthly_due.quantize(Decimal('0.01'))),
        supplier_count=len(supplier_codes),
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
]


async def get_supplier_payment_export(
    db: AsyncSession,
    format: str = 'xlsx',
    schedule_month: Optional[str] = None,
    supplier_name: Optional[str] = None,
    payment_month: Optional[str] = None,
    invoice_date_start: Optional[str] = None,
    invoice_date_end: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Tuple[Any, str, str]:
    """导出供应商付款排程（不分页），返回 (BytesIO, media_type, filename)。"""
    target_month = _resolve_month(schedule_month, payment_month)

    # 获取所有有发票记录的供应商（不限制排款月）
    all_suppliers = await _get_all_suppliers_with_invoices(db, supplier_name, invoice_date_start, invoice_date_end)

    # 获取当前排款月的发票数据
    filtered = await _fetch_filtered_invoices(db, target_month, supplier_name, invoice_date_start, invoice_date_end)
    monthly_items = _aggregate_invoices(filtered, target_month)

    # 创建月到期应付金额映射
    monthly_map = {it['supplier_code']: it for it in monthly_items}

    # 获取不在当前排款月的供应商的全部发票明细
    not_in_month_codes = [s['supplier_code'] for s in all_suppliers if s['supplier_code'] not in monthly_map]
    all_invoices_map = await _get_supplier_all_invoices(db, not_in_month_codes, supplier_name)

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
    await _fill_total_payable(db, items, supplier_name)

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
        })

    svc = GenericExportService(EXPORT_COLUMNS, export_rows, sheet_name='供应商付款排程')

    if format == 'csv':
        output = svc.to_csv()
        return output, 'text/csv; charset=utf-8', 'supplier_payment.csv'
    else:
        output = svc.to_xlsx()
        return output, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'supplier_payment.xlsx'
