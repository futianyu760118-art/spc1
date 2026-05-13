"""异常与质量中心 — 问题日志 API（只读 + CSV导入）"""

import tempfile
import os
from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.exception.issue_log import IssueLog
from app.schemas.common import ResponseModel, PageResult
from app.schemas.exception.schemas import IssueLogOut, IssueLogCreate, IssueLogUpdate
from app.services.exception.import_exception_csv import import_issue_log_csv

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[IssueLogOut]])
async def list_issue_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("exceptions.issue_log", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if keyword:
        like = f'%{keyword}%'
        conditions.append(IssueLog.description.ilike(like) | IssueLog.recorder.ilike(like))

    count_q = select(func.count(IssueLog.id))
    query = select(IssueLog)
    if conditions:
        count_q = count_q.where(*conditions)
        query = query.where(*conditions)

    total = (await db.execute(count_q)).scalar()
    query = query.order_by(IssueLog.seq_no.asc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [IssueLogOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("/import", response_model=ResponseModel[dict])
async def import_issue_logs(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("exceptions.issue_log", "import")),
    db: AsyncSession = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or '')[1] or '.csv'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await import_issue_log_csv(tmp_path, db)
    finally:
        os.unlink(tmp_path)

    await log_audit(db, "issue_log", 0, "import", field_name="issue_log_csv", new_value=file.filename, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)


@router.post("", response_model=ResponseModel[IssueLogOut])
async def create_issue_log(
    data: IssueLogCreate,
    current_user: dict = Depends(PermissionChecker("exceptions.issue_log", "create")),
    db: AsyncSession = Depends(get_db),
):
    new_issue = IssueLog(**data.model_dump())
    db.add(new_issue)
    await db.flush()
    await log_audit(db, "issue_log", new_issue.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(new_issue)
    return ResponseModel(data=IssueLogOut.model_validate(new_issue))


@router.put("/{item_id}", response_model=ResponseModel[IssueLogOut])
async def update_issue_log(
    item_id: int,
    data: IssueLogUpdate,
    current_user: dict = Depends(PermissionChecker("exceptions.issue_log", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(IssueLog).where(IssueLog.id == item_id))
    issue = result.scalar_one_or_none()
    if not issue:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="问题日志不存在")
    
    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "issue_log", issue.id, "update", old_obj=issue, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(issue, field, value)
    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=IssueLogOut.model_validate(issue))


@router.delete("/{item_id}", response_model=ResponseModel[dict])
async def delete_issue_log(
    item_id: int,
    current_user: dict = Depends(PermissionChecker("exceptions.issue_log", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(IssueLog).where(IssueLog.id == item_id))
    issue = result.scalar_one_or_none()
    if not issue:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="问题日志不存在")
    
    await log_audit(db, "issue_log", issue.id, "delete", operator=current_user["username"])
    await db.delete(issue)
    await db.commit()
    return ResponseModel(data={"message": "删除成功"})
