"""规则配置中心 — 责任归属 API"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.rules.responsibility_map import ResponsibilityMap
from app.schemas.common import ResponseModel
from app.schemas.rules.schemas import ResponsibilityMapOut, ResponsibilityMapCreate, ResponsibilityMapUpdate

router = APIRouter()


@router.get("", response_model=ResponseModel[list[ResponsibilityMapOut]])
async def list_responsibilities(
    rule_item_code: str | None = None,
    department: str | None = None,
    current_user: dict = Depends(PermissionChecker("rules.responsibility", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ResponsibilityMap).order_by(ResponsibilityMap.rule_item_code, ResponsibilityMap.escalation_level)
    if rule_item_code:
        stmt = stmt.where(ResponsibilityMap.rule_item_code == rule_item_code)
    if department:
        stmt = stmt.where(ResponsibilityMap.department == department)
    result = await db.execute(stmt)
    items = [ResponsibilityMapOut.model_validate(row) for row in result.scalars().all()]
    return ResponseModel(data=items)


@router.post("", response_model=ResponseModel[ResponsibilityMapOut])
async def create_responsibility(
    data: ResponsibilityMapCreate,
    current_user: dict = Depends(PermissionChecker("rules.responsibility", "create")),
    db: AsyncSession = Depends(get_db),
):
    item = ResponsibilityMap(**data.model_dump(), created_by=current_user["username"])
    db.add(item)
    await db.flush()
    await log_audit(db, "responsibility_map", item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(item)
    return ResponseModel(data=ResponsibilityMapOut.model_validate(item))


@router.put("/{map_id}", response_model=ResponseModel[ResponsibilityMapOut])
async def update_responsibility(
    map_id: int,
    data: ResponsibilityMapUpdate,
    current_user: dict = Depends(PermissionChecker("rules.responsibility", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ResponsibilityMap).where(ResponsibilityMap.id == map_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="责任归属不存在")
    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "responsibility_map", item.id, "update", old_obj=item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return ResponseModel(data=ResponsibilityMapOut.model_validate(item))


@router.delete("/{map_id}", response_model=ResponseModel)
async def delete_responsibility(
    map_id: int,
    current_user: dict = Depends(PermissionChecker("rules.responsibility", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ResponsibilityMap).where(ResponsibilityMap.id == map_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="责任归属不存在")
    await log_audit(db, "responsibility_map", item.id, "delete", operator=current_user["username"])
    await db.delete(item)
    await db.commit()
    return ResponseModel(data=None, message="删除成功")
