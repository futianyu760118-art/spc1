"""Tool: 搜索采购开票/供应商付款记录"""

from typing import Any, Dict
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.purchase_invoice import PurchaseInvoice
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，匹配发票号、供应商名称、供应商编号",
        },
        "supplier_name": {
            "type": "string",
            "description": "供应商名称（模糊匹配）",
        },
        "supplier_code": {
            "type": "string",
            "description": "供应商编号",
        },
        "invoice_no": {
            "type": "string",
            "description": "发票号码",
        },
        "date_start": {
            "type": "string",
            "description": "开票日期开始 YYYY-MM-DD",
        },
        "date_end": {
            "type": "string",
            "description": "开票日期结束 YYYY-MM-DD",
        },
        "has_remain_payable": {
            "type": "boolean",
            "description": "是否只查有剩余应付金额的记录",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限，默认20",
        },
    },
    "required": [],
}


@register_tool(
    name="search_invoices",
    description="搜索采购开票和供应商付款记录。支持按供应商名称、供应商编号、发票号、开票日期范围、是否有剩余应付等条件查询。可查看开票金额、剩余应付、账期、结算方式等。",
    parameters=PARAMETERS,
    display_name="开票付款查询",
)
async def search_invoices(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    query = select(PurchaseInvoice)
    count_query = select(func.count(PurchaseInvoice.id))

    filters = []

    keyword = params.get("keyword")
    if keyword:
        like = f"%{keyword}%"
        filters.append(
            PurchaseInvoice.invoice_no.ilike(like)
            | PurchaseInvoice.supplier_name.ilike(like)
            | PurchaseInvoice.supplier_code.ilike(like)
        )

    supplier_name = params.get("supplier_name")
    if supplier_name:
        filters.append(PurchaseInvoice.supplier_name.ilike(f"%{supplier_name}%"))

    supplier_code = params.get("supplier_code")
    if supplier_code:
        filters.append(PurchaseInvoice.supplier_code.ilike(f"%{supplier_code}%"))

    invoice_no = params.get("invoice_no")
    if invoice_no:
        filters.append(PurchaseInvoice.invoice_no.ilike(f"%{invoice_no}%"))

    date_start = params.get("date_start")
    if date_start:
        try:
            filters.append(PurchaseInvoice.invoice_date >= datetime.strptime(date_start, "%Y-%m-%d").date())
        except ValueError:
            pass

    date_end = params.get("date_end")
    if date_end:
        try:
            filters.append(PurchaseInvoice.invoice_date <= datetime.strptime(date_end, "%Y-%m-%d").date())
        except ValueError:
            pass

    has_remain = params.get("has_remain_payable")
    if has_remain:
        filters.append(PurchaseInvoice.remain_payable > 0)

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    limit = params.get("limit")
    if limit:
        query = query.order_by(PurchaseInvoice.invoice_date.desc().nullslast()).limit(limit)
    else:
        query = query.order_by(PurchaseInvoice.invoice_date.desc().nullslast())
    result = await db.execute(query)
    rows = result.scalars().all()

    items = []
    for r in rows:
        items.append({
            "type": "invoice",
            "title": f"发票 {r.invoice_no}",
            "subtitle": f"{r.supplier_name or ''} | 开票日期 {r.invoice_date or ''}",
            "url": "/invoices",
            "tags": [t for t in [r.payment_term, r.settlement_method] if t],
            # 完整字段
            "invoice_no": r.invoice_no,
            "line_no": r.line_no,
            "invoice_date": str(r.invoice_date) if r.invoice_date else None,
            "supplier_id": r.supplier_id,
            "supplier_code": r.supplier_code,
            "supplier_name": r.supplier_name,
            "payment_term": r.payment_term,
            "settlement_method": r.settlement_method,
            "invoice_amount": float(r.invoice_amount) if r.invoice_amount else None,
            "remain_payable": float(r.remain_payable) if r.remain_payable else None,
        })

    return {"total": total, "items": items}
