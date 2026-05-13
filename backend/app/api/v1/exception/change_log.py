"""异常与质量中心 — 变更日志 API（只读 + CSV导入）"""

import tempfile
import os
from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.exception.change_log import ChangeLog
from app.schemas.common import ResponseModel, PageResult
from app.schemas.exception.schemas import ChangeLogOut, ChangeLogCreate, ChangeLogUpdate
from app.services.exception.import_exception_csv import import_change_log_csv

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[ChangeLogOut]])
async def list_change_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("exceptions.change_log", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if keyword:
        like = f'%{keyword}%'
        conditions.append(ChangeLog.change_content.ilike(like) | ChangeLog.modifier.ilike(like))

    count_q = select(func.count(ChangeLog.id))
    query = select(ChangeLog)
    if conditions:
        count_q = count_q.where(*conditions)
        query = query.where(*conditions)

    total = (await db.execute(count_q)).scalar()
    query = query.order_by(ChangeLog.seq_no.asc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [ChangeLogOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("/import", response_model=ResponseModel[dict])
async def import_change_logs(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("exceptions.change_log", "import")),
    db: AsyncSession = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or '')[1] or '.csv'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await import_change_log_csv(tmp_path, db)
    finally:
        os.unlink(tmp_path)

    await log_audit(db, "change_log", 0, "import", field_name="change_log_csv", new_value=file.filename, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)


@router.post("", response_model=ResponseModel[ChangeLogOut])
async def create_change_log(
    data: ChangeLogCreate,
    current_user: dict = Depends(PermissionChecker("exceptions.change_log", "create")),
    db: AsyncSession = Depends(get_db),
):
    new_change = ChangeLog(**data.model_dump())
    db.add(new_change)
    await db.flush()
    await log_audit(db, "change_log", new_change.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(new_change)
    return ResponseModel(data=ChangeLogOut.model_validate(new_change))


@router.put("/{item_id}", response_model=ResponseModel[ChangeLogOut])
async def update_change_log(
    item_id: int,
    data: ChangeLogUpdate,
    current_user: dict = Depends(PermissionChecker("exceptions.change_log", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ChangeLog).where(ChangeLog.id == item_id))
    change = result.scalar_one_or_none()
    if not change:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="变更日志不存在")
    
    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "change_log", change.id, "update", old_obj=change, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(change, field, value)
    await db.commit()
    await db.refresh(change)
    return ResponseModel(data=ChangeLogOut.model_validate(change))


@router.delete("/{item_id}", response_model=ResponseModel[dict])
async def delete_change_log(
    item_id: int,
    current_user: dict = Depends(PermissionChecker("exceptions.change_log", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ChangeLog).where(ChangeLog.id == item_id))
    change = result.scalar_one_or_none()
    if not change:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="变更日志不存在")
    
    await log_audit(db, "change_log", change.id, "delete", operator=current_user["username"])
    await db.delete(change)
    await db.commit()
    return ResponseModel(data={"message": "删除成功"})
