"""物料齐套中心 — 问题物料 API"""

import tempfile
import os
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.material.material_issue import MaterialIssue
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import MaterialIssueOut, MaterialIssueCreate, MaterialIssueUpdate
from app.services.material.import_material_csv import import_material_issue_csv

router = APIRouter()


SORT_COLUMNS = {
    'year': MaterialIssue.year,
    'week_no': MaterialIssue.week_no,
    'department': MaterialIssue.department,
    'category': MaterialIssue.category,
    'issue_date': MaterialIssue.issue_date,
    'reporter': MaterialIssue.reporter,
    'deadline': MaterialIssue.deadline,
    'responsible_dept': MaterialIssue.responsible_dept,
    'responsible_person': MaterialIssue.responsible_person,
    'audit_score': MaterialIssue.audit_score,
    'status': MaterialIssue.status,
}


@router.get("", response_model=ResponseModel[PageResult[MaterialIssueOut]])
async def list_material_issues(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    week_no: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.issues", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if department:
        conditions.append(MaterialIssue.department == department)
    if status:
        conditions.append(MaterialIssue.status == status)
    if year:
        conditions.append(MaterialIssue.year == year)
    if week_no:
        conditions.append(MaterialIssue.week_no == week_no)
    if keyword:
        like = f'%{keyword}%'
        conditions.append(
            MaterialIssue.description.ilike(like)
            | MaterialIssue.reporter.ilike(like)
            | MaterialIssue.responsible_person.ilike(like)
        )

    count_q = select(func.count(MaterialIssue.id))
    query = select(MaterialIssue)
    if conditions:
        count_q = count_q.where(*conditions)
        query = query.where(*conditions)

    total = (await db.execute(count_q)).scalar()

    order_clauses = []
    if sort_by and sort_by in SORT_COLUMNS:
        col = SORT_COLUMNS[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    if not order_clauses:
        order_clauses = [MaterialIssue.year.desc(), MaterialIssue.week_no.desc()]

    query = query.order_by(*order_clauses).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [MaterialIssueOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[MaterialIssueOut])
async def create_material_issue(
    data: MaterialIssueCreate,
    current_user: dict = Depends(PermissionChecker("materials.issues", "create")),
    db: AsyncSession = Depends(get_db),
):
    issue = MaterialIssue(**data.model_dump())
    db.add(issue)
    await db.flush()
    await log_audit(db, "material_issue", issue.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=MaterialIssueOut.model_validate(issue))


@router.put("/{issue_id}", response_model=ResponseModel[MaterialIssueOut])
async def update_material_issue(
    issue_id: int,
    data: MaterialIssueUpdate,
    current_user: dict = Depends(PermissionChecker("materials.issues", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MaterialIssue).where(MaterialIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="问题记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "material_issue", issue.id, "update", old_obj=issue, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(issue, field, value)
    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=MaterialIssueOut.model_validate(issue))


@router.delete("/{issue_id}", response_model=ResponseModel[dict])
async def delete_material_issue(
    issue_id: int,
    current_user: dict = Depends(PermissionChecker("materials.issues", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MaterialIssue).where(MaterialIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="问题记录不存在")
    await log_audit(db, "material_issue", issue.id, "delete", operator=current_user["username"])
    await db.delete(issue)
    await db.commit()
    return ResponseModel(data={"deleted": issue_id})


@router.post("/import", response_model=ResponseModel[dict])
async def import_material_issues(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("materials.issues", "import")),
    db: AsyncSession = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or '')[1] or '.csv'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await import_material_issue_csv(tmp_path, db)
    finally:
        os.unlink(tmp_path)

    await log_audit(db, "material_issue", 0, "import", field_name="material_issue_csv", new_value=file.filename, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)
