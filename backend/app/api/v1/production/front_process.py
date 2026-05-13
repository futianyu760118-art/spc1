"""生产协同中心 — 前道管理 API"""

import tempfile
import os
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.production.process_progress import ProcessProgress
from app.schemas.common import ResponseModel, PageResult
from app.schemas.production.schemas import ProcessProgressOut, ProcessProgressCreate, ProcessProgressUpdate
from app.services.production.import_production_csv import import_front_process_csv

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[ProcessProgressOut]])
async def list_front_process(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    order_no: Optional[str] = Query(None),
    model_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("production.front_process", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = [ProcessProgress.process_type == 'front_process']
    if order_no:
        base.append(ProcessProgress.order_no.ilike(f'%{order_no}%'))
    if model_code:
        base.append(ProcessProgress.model_code.ilike(f'%{model_code}%'))
    if status:
        base.append(ProcessProgress.status == status)
    if keyword:
        like = f'%{keyword}%'
        base.append(
            ProcessProgress.model_code.ilike(like)
            | ProcessProgress.sale_order_no.ilike(like)
            | ProcessProgress.product_name.ilike(like)
        )

    total_result = await db.execute(select(func.count(ProcessProgress.id)).where(*base))
    total = total_result.scalar()

    query = (
        select(ProcessProgress)
        .where(*base)
        .order_by(ProcessProgress.delivery_date.asc().nullslast(), ProcessProgress.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = [ProcessProgressOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[ProcessProgressOut])
async def create_front_process(
    data: ProcessProgressCreate,
    current_user: dict = Depends(PermissionChecker("production.front_process", "create")),
    db: AsyncSession = Depends(get_db),
):
    data.process_type = 'front_process'
    rec = ProcessProgress(**data.model_dump(), data_source='manual')
    db.add(rec)
    await db.flush()
    await log_audit(db, "process_progress", rec.id, "create", field_name="front_process", operator=current_user["username"])
    await db.commit()
    await db.refresh(rec)
    return ResponseModel(data=ProcessProgressOut.model_validate(rec))


@router.put("/{record_id}", response_model=ResponseModel[ProcessProgressOut])
async def update_front_process(
    record_id: int,
    data: ProcessProgressUpdate,
    current_user: dict = Depends(PermissionChecker("production.front_process", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProcessProgress).where(ProcessProgress.id == record_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "process_progress", rec.id, "update", old_obj=rec, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(rec, field, value)
    await db.commit()
    await db.refresh(rec)
    return ResponseModel(data=ProcessProgressOut.model_validate(rec))


@router.post("/import", response_model=ResponseModel[dict])
async def import_front_process(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("production.front_process", "import")),
    db: AsyncSession = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or '')[1] or '.csv'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await import_front_process_csv(tmp_path, db)
    finally:
        os.unlink(tmp_path)

    await log_audit(db, "process_progress", 0, "import", field_name="front_process_csv", new_value=file.filename, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)
