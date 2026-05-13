from datetime import date, datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.exception.risk_issue import RiskIssue
from app.schemas.common import ResponseModel, PageResult
from app.schemas.exception.schemas import RiskIssueOut, RiskIssueCreate, RiskIssueUpdate
from app.services.exception.risk_engine import ISSUE_TYPE_PREFIX

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[RiskIssueOut]])
async def list_issues(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    issue_type: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("exceptions.pool", "read")),
    db: AsyncSession = Depends(get_db),
):
    query = select(RiskIssue)
    count_query = select(func.count(RiskIssue.id))

    filters = []
    if status:
        filters.append(RiskIssue.status == status)
    if risk_level:
        filters.append(RiskIssue.risk_level == risk_level)
    if issue_type:
        filters.append(RiskIssue.issue_type == issue_type)
    if owner:
        filters.append(RiskIssue.owner == owner)

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(RiskIssue.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [RiskIssueOut.model_validate(row) for row in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[RiskIssueOut])
async def create_issue(
    data: RiskIssueCreate,
    current_user: dict = Depends(PermissionChecker("exceptions.pool", "create")),
    db: AsyncSession = Depends(get_db),
):
    # 统一编号: {类型缩写}-{YYYYMMDD}-{当日序列号}
    issue_type = data.issue_type or "manual"
    prefix = ISSUE_TYPE_PREFIX.get(issue_type, "MN")
    today_str = date.today().strftime("%Y%m%d")
    like_pattern = f"{prefix}-{today_str}-%"
    max_result = await db.execute(
        select(func.max(RiskIssue.issue_no)).where(RiskIssue.issue_no.like(like_pattern))
    )
    max_no = max_result.scalar_one_or_none()
    seq = int(max_no.split("-")[-1]) + 1 if max_no else 1
    issue_no = f"{prefix}-{today_str}-{seq:04d}"

    issue = RiskIssue(**data.model_dump(), issue_no=issue_no)
    db.add(issue)
    await db.flush()
    await log_audit(db, "risk_issue", issue.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=RiskIssueOut.model_validate(issue))


@router.put("/{issue_id}", response_model=ResponseModel[RiskIssueOut])
async def update_issue(
    issue_id: int,
    data: RiskIssueUpdate,
    current_user: dict = Depends(PermissionChecker("exceptions.pool", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RiskIssue).where(RiskIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="异常问题不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "risk_issue", issue.id, "update", old_obj=issue, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(issue, field, value)

    if data.status == "closed":
        issue.closed_at = datetime.now()
    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=RiskIssueOut.model_validate(issue))
