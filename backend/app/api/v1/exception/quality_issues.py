"""异常与质量中心 — 品质异常 API（CRUD）"""

from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.exception.quality_issue import QualityIssue
from app.schemas.common import ResponseModel, PageResult
from app.schemas.exception.schemas import QualityIssueOut, QualityIssueCreate, QualityIssueUpdate

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[QualityIssueOut]])
async def list_quality_issues(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    submit_dept: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if submit_dept:
        conditions.append(QualityIssue.submit_dept == submit_dept)
    if status:
        conditions.append(QualityIssue.status == status)
    if keyword:
        like = f'%{keyword}%'
        conditions.append(
            QualityIssue.order_no.ilike(like)
            | QualityIssue.product_code.ilike(like)
            | QualityIssue.submit_dept.ilike(like)
            | QualityIssue.submitter.ilike(like)
            | QualityIssue.product_name.ilike(like)
            | QualityIssue.process.ilike(like)
            | QualityIssue.defect_type.ilike(like)
            | QualityIssue.description.ilike(like)
            | QualityIssue.root_cause.ilike(like)
            | QualityIssue.responsible_person.ilike(like)
            | QualityIssue.responsible_dept.ilike(like)
        )

    count_q = select(func.count(QualityIssue.id))
    query = select(QualityIssue)
    if conditions:
        count_q = count_q.where(*conditions)
        query = query.where(*conditions)

    total = (await db.execute(count_q)).scalar()
    query = query.order_by(QualityIssue.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [QualityIssueOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[QualityIssueOut])
async def create_quality_issue(
    data: QualityIssueCreate,
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "create")),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(select(func.count(QualityIssue.id)))
    count = count_result.scalar()
    year = data.submit_date.year if data.submit_date else date.today().year
    issue_no = f"QI-{year}-{count + 1:04d}"

    issue = QualityIssue(**data.model_dump(), issue_no=issue_no)
    db.add(issue)
    await db.flush()
    await log_audit(db, "quality_issue", issue.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=QualityIssueOut.model_validate(issue))


@router.put("/{issue_id}", response_model=ResponseModel[QualityIssueOut])
async def update_quality_issue(
    issue_id: int,
    data: QualityIssueUpdate,
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(QualityIssue).where(QualityIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="品质异常不存在")

    update_data = data.model_dump(exclude_unset=True, include={"status"})
    await log_audit(db, "quality_issue", issue.id, "update", old_obj=issue, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(issue, field, value)

    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=QualityIssueOut.model_validate(issue))


@router.delete("/{issue_id}", response_model=ResponseModel[dict])
async def delete_quality_issue(
    issue_id: int,
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(QualityIssue).where(QualityIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="品质异常不存在")
    await log_audit(db, "quality_issue", issue.id, "delete", operator=current_user["username"])
    await db.delete(issue)
    await db.commit()
    return ResponseModel(data={"deleted": issue_id})
