"""规则配置中心 — 状态字典 API"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.rules.status_dictionary import StatusDictionary
from app.schemas.common import ResponseModel
from app.schemas.rules.schemas import StatusDictionaryOut, StatusDictionaryCreate, StatusDictionaryUpdate

router = APIRouter()


@router.get("", response_model=ResponseModel[list[StatusDictionaryOut]])
async def list_status_dict(
    status_type: str | None = None,
    current_user: dict = Depends(PermissionChecker("rules.status_dict", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(StatusDictionary).order_by(StatusDictionary.status_type, StatusDictionary.sort_order)
    if status_type:
        stmt = stmt.where(StatusDictionary.status_type == status_type)
    result = await db.execute(stmt)
    items = [StatusDictionaryOut.model_validate(row) for row in result.scalars().all()]
    return ResponseModel(data=items)


@router.post("", response_model=ResponseModel[StatusDictionaryOut])
async def create_status_dict(
    data: StatusDictionaryCreate,
    current_user: dict = Depends(PermissionChecker("rules.status_dict", "create")),
    db: AsyncSession = Depends(get_db),
):
    item = StatusDictionary(**data.model_dump(), created_by=current_user["username"])
    db.add(item)
    await db.flush()
    await log_audit(db, "status_dictionary", item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(item)
    return ResponseModel(data=StatusDictionaryOut.model_validate(item))


@router.put("/{dict_id}", response_model=ResponseModel[StatusDictionaryOut])
async def update_status_dict(
    dict_id: int,
    data: StatusDictionaryUpdate,
    current_user: dict = Depends(PermissionChecker("rules.status_dict", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(StatusDictionary).where(StatusDictionary.id == dict_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="状态字典不存在")
    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "status_dictionary", item.id, "update", old_obj=item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return ResponseModel(data=StatusDictionaryOut.model_validate(item))


@router.delete("/{dict_id}", response_model=ResponseModel)
async def delete_status_dict(
    dict_id: int,
    current_user: dict = Depends(PermissionChecker("rules.status_dict", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(StatusDictionary).where(StatusDictionary.id == dict_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="状态字典不存在")
    await log_audit(db, "status_dictionary", item.id, "delete", operator=current_user["username"])
    await db.delete(item)
    await db.commit()
    return ResponseModel(data=None, message="删除成功")
