"""供应商即时沟通消息 API"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.material.supplier_message import SupplierMessage
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import SupplierMessageCreate, SupplierMessageOut

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[SupplierMessageOut]])
async def list_supplier_messages(
    supplier_name: str = Query(..., description="供应商名称"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    after_id: Optional[int] = Query(None, description="获取此ID之后的消息"),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = [SupplierMessage.supplier_name == supplier_name]
    if after_id:
        base.append(SupplierMessage.id > after_id)

    total_result = await db.execute(select(func.count(SupplierMessage.id)).where(*base))
    total = total_result.scalar() or 0

    query = (
        select(SupplierMessage)
        .where(*base)
        .order_by(SupplierMessage.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    rows = result.scalars().all()

    items = [SupplierMessageOut.model_validate(r) for r in reversed(rows)]
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[SupplierMessageOut])
async def send_supplier_message(
    data: SupplierMessageCreate,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    msg = SupplierMessage(
        supplier_name=data.supplier_name,
        supplier_account=data.supplier_account,
        sender_id=int(current_user["sub"]),
        sender_name=current_user.get("username", current_user.get("sub", "")),
        content=data.content,
        po_no=data.po_no,
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return ResponseModel(data=SupplierMessageOut.model_validate(msg))


@router.get("/unread", response_model=ResponseModel)
async def get_unread_messages(
    supplier_name: Optional[str] = Query(None),
    after_id: Optional[int] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = []
    if supplier_name:
        base.append(SupplierMessage.supplier_name == supplier_name)
    if after_id:
        base.append(SupplierMessage.id > after_id)

    query = (
        select(SupplierMessage)
        .where(*base)
        .order_by(SupplierMessage.id.desc())
        .limit(50)
    )
    result = await db.execute(query)
    rows = result.scalars().all()

    items = [SupplierMessageOut.model_validate(r) for r in reversed(rows)]
    return ResponseModel(data={"items": [item.model_dump(mode='json') for item in items], "count": len(items)})