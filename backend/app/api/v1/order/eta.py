from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.eta_update import ETAUpdate
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import ETAUpdateRequest, ETAUpdateOut, PurchaseOrderOut
from app.services.order.eta_service import update_purchase_order_eta

router = APIRouter()


@router.put("/purchase-orders/{po_no}/eta", response_model=ResponseModel[PurchaseOrderOut])
async def update_eta(
    po_no: str,
    data: ETAUpdateRequest,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        po = await update_purchase_order_eta(
            db, po_no=po_no, new_eta=data.new_eta, updater=current_user["username"],
            update_reason=data.update_reason, remark=data.remark,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await db.refresh(po)
    return ResponseModel(data=PurchaseOrderOut.model_validate(po))


@router.get("/purchase-orders/{po_no}/eta-history", response_model=ResponseModel[list[ETAUpdateOut]])
async def get_eta_history(
    po_no: str,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ETAUpdate)
        .where(ETAUpdate.po_no == po_no)
        .order_by(ETAUpdate.created_at.desc())
    )
    items = [ETAUpdateOut.model_validate(row) for row in result.scalars().all()]
    return ResponseModel(data=items)


@router.get("/pending-updates", response_model=ResponseModel[PageResult[PurchaseOrderOut]])
async def get_pending_eta_updates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    """需要更新 ETA 的 PO 列表（ETA 为空或已过期）"""
    from datetime import date

    query = select(PurchaseOrder).where(
        PurchaseOrder.po_status.in_(["placed", "accepted", "in_production"]),
        (PurchaseOrder.eta == None) | (PurchaseOrder.eta < date.today()),
    )
    count_query = select(func.count(PurchaseOrder.id)).where(
        PurchaseOrder.po_status.in_(["placed", "accepted", "in_production"]),
        (PurchaseOrder.eta == None) | (PurchaseOrder.eta < date.today()),
    )

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(PurchaseOrder.eta.asc().nullsfirst()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [PurchaseOrderOut.model_validate(row) for row in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))
