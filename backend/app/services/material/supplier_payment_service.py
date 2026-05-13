"""物料齐套中心 — 供应商付款排程服务

数据来源：直接基于 purchase_invoice 表聚合。
聚合规则（对齐用户 SQL）：
  内层子查询 hj：按 supplier_code 分组，WHERE TO_CHAR(invoice_date,'YYYY-MM')=target_month，SUM(remain_payable) → 月到期应付
  外层 INNER JOIN hj：按 supplier_code 分组，MAX(supplier_name/invoice_date/payment_term/settlement_method)，SUM(remain_payable)=总应付金额，
                       MIN(hj.月到期应付)=月到期应付金额
  INNER JOIN 含义：只显示该月有到期发票的供应商。
"""

from cProfile import label
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.purchase_invoice import PurchaseInvoice
from app.schemas.material.schemas import SupplierPaymentSummary


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
    'payment_term', 'payment_method', 'total_payable', 'monthly_due',
}


def _resolve_month(schedule_month: Optional[str], payment_month: Optional[str]) -> str:
    """统一为单一目标月份（YYYY-MM）。payment_month 优先，其次 schedule_month，最后当前月。"""
    return payment_month or schedule_month or _default_month()


def _build_outer_query(target_month: str, supplier_name: Optional[str]):
    """按用户 SQL 构建聚合查询：

    SELECT p.supplier_code,
           MAX(p.supplier_name), MAX(hj.invoice_date), MAX(p.payment_term),
           MAX(p.settlement_method),
           SUM(p.remain_payable)   AS total_payable,
           MIN(hj.monthly_due)     AS monthly_due
    FROM purchase_invoice p
    INNER JOIN (
        SELECT supplier_code,max(invoice_date) as invoice_date, SUM(remain_payable) AS monthly_due
        FROM purchase_invoice
        WHERE TO_CHAR(invoice_date,'YYYY-MM') = :target_month
        GROUP BY supplier_code
    ) hj ON hj.supplier_code = p.supplier_code
    GROUP BY p.supplier_code
    """
    hj = (
        select(
            PurchaseInvoice.supplier_code.label('supplier_code'),
            func.max(PurchaseInvoice.invoice_date).label('invoice_date'),
            func.sum(PurchaseInvoice.remain_payable).label('monthly_due'),
        )
        .where(func.to_char(PurchaseInvoice.invoice_date, 'YYYY-MM') == target_month)
        .group_by(PurchaseInvoice.supplier_code)
        .subquery('hj')
    )

    p = PurchaseInvoice
    stmt = (
        select(
            p.supplier_code.label('supplier_code'),
            func.max(p.supplier_name).label('supplier_name'),
            func.max(hj.c.invoice_date).label('invoice_date'),
            func.max(p.payment_term).label('payment_term'),
            func.max(p.settlement_method).label('payment_method'),
            func.sum(p.remain_payable).label('total_payable'),
            func.min(hj.c.monthly_due).label('monthly_due'),
        )
        .join(hj, hj.c.supplier_code == p.supplier_code)
        .group_by(p.supplier_code)
    )

    if supplier_name:
        stmt = stmt.where(p.supplier_name.ilike(f'%{supplier_name}%'))

    return stmt


def _row_to_dict(row, target_month: str) -> Dict[str, Any]:
    invoice_date = row['invoice_date']
    payment_term = row['payment_term']
    return {
        'supplier_code': row['supplier_code'] or '',
        'supplier_name': row['supplier_name'],
        'invoice_date': invoice_date.isoformat() if invoice_date else None,
        'payment_term': payment_term,
        'payment_method': row['payment_method'],
        'total_payable': float(row['total_payable']) if row['total_payable'] is not None else 0.0,
        'monthly_due': float(row['monthly_due']) if row['monthly_due'] is not None else 0.0,
        # 排款月 = 到票日期 + 账期天数（按行计算）
        'payment_month': _compute_payment_month(invoice_date, payment_term),
        # 兼容旧字段：目标月份
        'schedule_month': target_month,
    }


async def get_supplier_payment_list(
    db: AsyncSession,
    schedule_month: Optional[str] = None,
    supplier_name: Optional[str] = None,
    payment_month: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    target_month = _resolve_month(schedule_month, payment_month)

    stmt = _build_outer_query(target_month, supplier_name)
    result = await db.execute(stmt)
    rows = result.mappings().all()

    items: List[Dict[str, Any]] = [_row_to_dict(r, target_month) for r in rows]

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
) -> SupplierPaymentSummary:
    target_month = _resolve_month(schedule_month, payment_month)

    stmt = _build_outer_query(target_month, supplier_name)
    result = await db.execute(stmt)
    rows = result.mappings().all()

    total_payable = 0.0
    total_monthly_due = 0.0
    supplier_codes = set()
    for r in rows:
        if r['supplier_code']:
            supplier_codes.add(r['supplier_code'])
        if r['total_payable'] is not None:
            total_payable += float(r['total_payable'])
        if r['monthly_due'] is not None:
            total_monthly_due += float(r['monthly_due'])

    return SupplierPaymentSummary(
        total_payable=total_payable,
        total_monthly_due=total_monthly_due,
        supplier_count=len(supplier_codes),
    )
