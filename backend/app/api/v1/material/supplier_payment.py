"""物料齐套中心 — 供应商付款排程 API（基于 purchase_invoice 聚合，只读）"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.supplier_scope import get_supplier_name_scope
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import SupplierPaymentOut, SupplierPaymentSummary
from app.services.material.supplier_payment_service import (
    get_supplier_payment_list,
    get_supplier_payment_summary,
    get_supplier_payment_export,
)

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[SupplierPaymentOut]])
async def list_supplier_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    supplier_name: Optional[str] = Query(None),
    schedule_month: Optional[str] = Query(None, description="目标月份 YYYY-MM（兼容字段，等价于 payment_month）"),
    payment_month: Optional[str] = Query(None, description="排款月份 YYYY-MM：筛选排款月（到票日期+账期天数）等于该月的发票"),
    invoice_date_start: Optional[str] = Query(None, description="到票开始日期 YYYY-MM-DD"),
    invoice_date_end: Optional[str] = Query(None, description="到票结束日期 YYYY-MM-DD"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.supplier_payment", "read")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    items, total = await get_supplier_payment_list(
        db,
        schedule_month=schedule_month,
        supplier_name=supplier_scope or supplier_name,
        exact_supplier_name=bool(supplier_scope),
        payment_month=payment_month,
        invoice_date_start=invoice_date_start,
        invoice_date_end=invoice_date_end,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return ResponseModel(
        data=PageResult(total=total, page=page, page_size=page_size, items=items)
    )


@router.get("/summary", response_model=ResponseModel[SupplierPaymentSummary])
async def supplier_payment_summary(
    schedule_month: Optional[str] = Query(None, description="目标月份 YYYY-MM（兼容字段，等价于 payment_month）"),
    payment_month: Optional[str] = Query(None, description="排款月份 YYYY-MM：筛选排款月（到票日期+账期天数）等于该月的发票"),
    supplier_name: Optional[str] = Query(None),
    invoice_date_start: Optional[str] = Query(None, description="到票开始日期 YYYY-MM-DD"),
    invoice_date_end: Optional[str] = Query(None, description="到票结束日期 YYYY-MM-DD"),
    current_user: dict = Depends(PermissionChecker("materials.supplier_payment", "read")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    summary = await get_supplier_payment_summary(
        db, schedule_month=schedule_month, supplier_name=supplier_scope or supplier_name, exact_supplier_name=bool(supplier_scope), payment_month=payment_month,
        invoice_date_start=invoice_date_start, invoice_date_end=invoice_date_end
    )
    return ResponseModel(data=summary)


@router.get("/export")
async def export_supplier_payment(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    schedule_month: Optional[str] = Query(None, description="目标月份 YYYY-MM（兼容字段，等价于 payment_month）"),
    payment_month: Optional[str] = Query(None, description="排款月份 YYYY-MM：筛选排款月（到票日期+账期天数）等于该月的发票"),
    supplier_name: Optional[str] = Query(None),
    invoice_date_start: Optional[str] = Query(None, description="到票开始日期 YYYY-MM-DD"),
    invoice_date_end: Optional[str] = Query(None, description="到票结束日期 YYYY-MM-DD"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.supplier_payment", "read")),
    db: AsyncSession = Depends(get_db),
):
    """导出供应商付款排程（支持筛选 + 排序，不分页）"""
    supplier_scope = await get_supplier_name_scope(current_user, db)
    output, media_type, filename = await get_supplier_payment_export(
        db,
        format=format,
        schedule_month=schedule_month,
        supplier_name=supplier_scope or supplier_name,
        exact_supplier_name=bool(supplier_scope),
        payment_month=payment_month,
        invoice_date_start=invoice_date_start,
        invoice_date_end=invoice_date_end,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return StreamingResponse(output, media_type=media_type, headers={"Content-Disposition": f"attachment; filename={filename}"})
