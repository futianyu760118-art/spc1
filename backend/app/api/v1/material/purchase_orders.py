from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.core.supplier_scope import get_supplier_name_scope
from app.models.material.purchase_order import PurchaseOrder
from app.models.basicdata.audit_log import AuditLog
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import (
    PurchaseOrderOut, PurchaseOrderCreate, PurchaseOrderUpdate,
    POStatusUpdate, POTimelineItem,
)
from app.services.common.sync_filter import get_purchase_order_sync_filters

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[PurchaseOrderOut]])
async def list_purchase_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    po_status: Optional[str] = Query(None),
    supplier_code: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    owner_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    sync_filters = await get_purchase_order_sync_filters(db)
    query = select(PurchaseOrder).where(*sync_filters)
    count_query = select(func.count(PurchaseOrder.id)).where(*sync_filters)
    if supplier_scope:
        query = query.where(PurchaseOrder.supplier_name == supplier_scope)
        count_query = count_query.where(PurchaseOrder.supplier_name == supplier_scope)

    if po_status:
        query = query.where(PurchaseOrder.po_status == po_status)
        count_query = count_query.where(PurchaseOrder.po_status == po_status)
    if supplier_code and not supplier_scope:
        query = query.where(PurchaseOrder.supplier_code == supplier_code)
        count_query = count_query.where(PurchaseOrder.supplier_code == supplier_code)
    if owner:
        query = query.where(PurchaseOrder.owner == owner)
        count_query = count_query.where(PurchaseOrder.owner == owner)
    if owner_id is not None:
        query = query.where(PurchaseOrder.owner_id == owner_id)
        count_query = count_query.where(PurchaseOrder.owner_id == owner_id)
    if keyword:
        like_expr = f"%{keyword}%"
        kw_filter = (
            PurchaseOrder.po_no.ilike(like_expr)
            | PurchaseOrder.material_code.ilike(like_expr)
            | PurchaseOrder.supplier_name.ilike(like_expr)
            | PurchaseOrder.material_name.ilike(like_expr)
        )
        query = query.where(kw_filter)
        count_query = count_query.where(kw_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(PurchaseOrder.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [PurchaseOrderOut.model_validate(row) for row in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.get("/{po_no}", response_model=ResponseModel[PurchaseOrderOut])
async def get_purchase_order(
    po_no: str,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    sync_filters = await get_purchase_order_sync_filters(db)
    conditions = [PurchaseOrder.po_no == po_no] + sync_filters
    if supplier_scope:
        conditions.append(PurchaseOrder.supplier_name == supplier_scope)
    result = await db.execute(select(PurchaseOrder).where(*conditions))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="PO不存在")
    return ResponseModel(data=PurchaseOrderOut.model_validate(po))


@router.put("/{po_no}/status", response_model=ResponseModel[PurchaseOrderOut])
async def update_po_status(
    po_no: str,
    data: POStatusUpdate,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "update")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    sync_filters = await get_purchase_order_sync_filters(db)
    conditions = [PurchaseOrder.po_no == po_no] + sync_filters
    if supplier_scope:
        conditions.append(PurchaseOrder.supplier_name == supplier_scope)
    result = await db.execute(select(PurchaseOrder).where(*conditions))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="PO不存在")

    old_status = po.po_status
    po.po_status = data.po_status
    if data.remark:
        po.remark = data.remark

    await log_audit(db, "purchase_order", po.id, "update", field_name="po_status", old_value=old_status, new_value=data.po_status, operator=current_user["username"])
    await db.commit()
    await db.refresh(po)
    return ResponseModel(data=PurchaseOrderOut.model_validate(po))


@router.get("/{po_no}/timeline", response_model=ResponseModel[list[POTimelineItem]])
async def get_po_timeline(
    po_no: str,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    sync_filters = await get_purchase_order_sync_filters(db)
    conditions = [PurchaseOrder.po_no == po_no] + sync_filters
    if supplier_scope:
        conditions.append(PurchaseOrder.supplier_name == supplier_scope)
    po_result = await db.execute(select(PurchaseOrder).where(*conditions))
    po = po_result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="PO不存在")

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.table_name == "purchase_order", AuditLog.record_id == po.id)
        .order_by(AuditLog.operated_at.asc())
    )
    logs = result.scalars().all()

    timeline = [
        POTimelineItem(
            timestamp=log.operated_at,
            action=f"{log.field_name}: {log.old_value} → {log.new_value}",
            old_value=log.old_value,
            new_value=log.new_value,
            operator=log.operator,
        )
        for log in logs
    ]
    return ResponseModel(data=timeline)
