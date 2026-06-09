"""Production schedule plan API."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.production.schedule_plan import ProductionSchedulePlan
from app.schemas.common import PageResult, ResponseModel
from app.schemas.production.schemas import (
    ProductionSchedulePlanCreate,
    ProductionSchedulePlanOut,
    ProductionSchedulePlanUpdate,
)

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[ProductionSchedulePlanOut]])
async def list_schedule_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if department:
        conditions.append(ProductionSchedulePlan.department == department)
    if status:
        conditions.append(ProductionSchedulePlan.status == status)
    if date_start:
        conditions.append(ProductionSchedulePlan.plan_date >= date_start)
    if date_end:
        conditions.append(ProductionSchedulePlan.plan_date <= date_end)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            or_(
                ProductionSchedulePlan.order_no.ilike(like),
                ProductionSchedulePlan.product_code.ilike(like),
                ProductionSchedulePlan.model_code.ilike(like),
                ProductionSchedulePlan.owner.ilike(like),
                ProductionSchedulePlan.remark.ilike(like),
            )
        )

    total = (await db.execute(select(func.count(ProductionSchedulePlan.id)).where(*conditions))).scalar() or 0
    result = await db.execute(
        select(ProductionSchedulePlan)
        .where(*conditions)
        .order_by(ProductionSchedulePlan.plan_date.desc(), ProductionSchedulePlan.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [ProductionSchedulePlanOut.model_validate(row) for row in result.scalars().all()]
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[ProductionSchedulePlanOut])
async def create_schedule_plan(
    data: ProductionSchedulePlanCreate,
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "create")),
    db: AsyncSession = Depends(get_db),
):
    record = ProductionSchedulePlan(**data.model_dump(), created_by=current_user["username"])
    db.add(record)
    await db.flush()
    await log_audit(db, "production_schedule_plan", record.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(record)
    return ResponseModel(data=ProductionSchedulePlanOut.model_validate(record))


@router.put("/{record_id}", response_model=ResponseModel[ProductionSchedulePlanOut])
async def update_schedule_plan(
    record_id: int,
    data: ProductionSchedulePlanUpdate,
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "update")),
    db: AsyncSession = Depends(get_db),
):
    record = (await db.execute(select(ProductionSchedulePlan).where(ProductionSchedulePlan.id == record_id))).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="计划不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "production_schedule_plan", record.id, "update", old_obj=record, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(record, field, value)
    await db.commit()
    await db.refresh(record)
    return ResponseModel(data=ProductionSchedulePlanOut.model_validate(record))


@router.delete("/{record_id}", response_model=ResponseModel[dict])
async def delete_schedule_plan(
    record_id: int,
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "delete")),
    db: AsyncSession = Depends(get_db),
):
    record = (await db.execute(select(ProductionSchedulePlan).where(ProductionSchedulePlan.id == record_id))).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="计划不存在")

    await log_audit(db, "production_schedule_plan", record.id, "delete", operator=current_user["username"])
    await db.delete(record)
    await db.commit()
    return ResponseModel(data={"deleted": record_id})
