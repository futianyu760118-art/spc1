"""物料齐套中心 — 供应商付款排程 API（基于 purchase_invoice 聚合，只读）"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import SupplierPaymentOut, SupplierPaymentSummary
from app.services.material.supplier_payment_service import (
    get_supplier_payment_list,
    get_supplier_payment_summary,
)

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[SupplierPaymentOut]])
async def list_supplier_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    supplier_name: Optional[str] = Query(None),
    schedule_month: Optional[str] = Query(None, description="目标月份 YYYY-MM（兼容字段，等价于 payment_month）"),
    payment_month: Optional[str] = Query(None, description="目标月份 YYYY-MM：筛选 invoice_date 在该月的发票作为月到期应付"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.supplier_payment", "read")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await get_supplier_payment_list(
        db,
        schedule_month=schedule_month,
        supplier_name=supplier_name,
        payment_month=payment_month,
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
    payment_month: Optional[str] = Query(None, description="目标月份 YYYY-MM：筛选 invoice_date 在该月的发票作为月到期应付"),
    supplier_name: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.supplier_payment", "read")),
    db: AsyncSession = Depends(get_db),
):
    summary = await get_supplier_payment_summary(
        db, schedule_month=schedule_month, supplier_name=supplier_name, payment_month=payment_month
    )
    return ResponseModel(data=summary)
