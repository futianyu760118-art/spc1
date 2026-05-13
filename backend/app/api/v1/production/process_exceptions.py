"""生产协同中心 — 工序异常池 API"""

import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.production.process_exception import ProcessException
from app.schemas.common import ResponseModel, PageResult
from app.schemas.production.schemas import ProcessExceptionOut, ProcessExceptionCreate, ProcessExceptionUpdate

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[ProcessExceptionOut]])
async def list_exceptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    process_type: Optional[str] = Query(None),
    exception_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("production.exceptions", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = []
    if process_type:
        base.append(ProcessException.process_type == process_type)
    if exception_type:
        base.append(ProcessException.exception_type == exception_type)
    if severity:
        base.append(ProcessException.severity == severity)
    if status:
        base.append(ProcessException.status == status)
    if keyword:
        like = f'%{keyword}%'
        base.append(
            ProcessException.order_no.ilike(like)
            | ProcessException.model_code.ilike(like)
            | ProcessException.description.ilike(like)
        )

    total_result = await db.execute(select(func.count(ProcessException.id)).where(*base))
    total = total_result.scalar()

    query = (
        select(ProcessException)
        .where(*base)
        .order_by(ProcessException.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = [ProcessExceptionOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[ProcessExceptionOut])
async def create_exception(
    data: ProcessExceptionCreate,
    current_user: dict = Depends(PermissionChecker("production.exceptions", "create")),
    db: AsyncSession = Depends(get_db),
):
    uid = uuid.uuid4().hex[:8].upper()
    pt = (data.process_type or 'UNK')[:4].upper()
    exception_no = f"PEX-{pt}-{uid}"
    rec = ProcessException(**data.model_dump(), exception_no=exception_no)
    db.add(rec)
    await db.flush()
    await log_audit(db, "process_exception", rec.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(rec)
    return ResponseModel(data=ProcessExceptionOut.model_validate(rec))


@router.put("/{record_id}", response_model=ResponseModel[ProcessExceptionOut])
async def update_exception(
    record_id: int,
    data: ProcessExceptionUpdate,
    current_user: dict = Depends(PermissionChecker("production.exceptions", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProcessException).where(ProcessException.id == record_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "process_exception", rec.id, "update", old_obj=rec, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(rec, field, value)
    await db.commit()
    await db.refresh(rec)
    return ResponseModel(data=ProcessExceptionOut.model_validate(rec))


@router.delete("/{record_id}", response_model=ResponseModel[dict])
async def delete_exception(
    record_id: int,
    current_user: dict = Depends(PermissionChecker("production.exceptions", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProcessException).where(ProcessException.id == record_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")

    await log_audit(db, "process_exception", rec.id, "delete", operator=current_user["username"])
    await db.delete(rec)
    await db.commit()
    return ResponseModel(data={"deleted": record_id})
