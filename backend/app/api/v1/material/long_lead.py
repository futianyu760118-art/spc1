"""物料齐套中心 — 长交期物料池 API（派生视图 + 注解表）"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.core.supplier_scope import get_supplier_name_scope
from app.models.material.long_lead_material import LongLeadMaterial
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import LongLeadMaterialOut, LongLeadMaterialUpdate, EnsureAnnotationRequest
from app.services.material.long_lead_analysis_service import (
    get_long_lead_pool,
    scan_and_create_annotations,
)

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult])
async def list_long_lead(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    supplier_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.long_lead", "read")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    items, total, stats = await get_long_lead_pool(
        db,
        keyword=keyword,
        supplier_name=supplier_scope or supplier_name,
        exact_supplier_name=bool(supplier_scope),
        status=status,
        risk_level=risk_level,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return ResponseModel(data=PageResult(
        total=total, page=page, page_size=page_size,
        items=[item.model_dump() for item in items],
        stats=stats,
    ))


@router.put("/{item_id}", response_model=ResponseModel[LongLeadMaterialOut])
async def update_long_lead(
    item_id: int,
    data: LongLeadMaterialUpdate,
    current_user: dict = Depends(PermissionChecker("materials.long_lead", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LongLeadMaterial).where(LongLeadMaterial.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="注解记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "long_lead_material", item.id, "update", old_obj=item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return ResponseModel(data=LongLeadMaterialOut.model_validate(item))


@router.delete("/{item_id}", response_model=ResponseModel[dict])
async def delete_long_lead(
    item_id: int,
    current_user: dict = Depends(PermissionChecker("materials.long_lead", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LongLeadMaterial).where(LongLeadMaterial.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="注解记录不存在")
    await log_audit(db, "long_lead_material", item.id, "delete", operator=current_user["username"])
    await db.delete(item)
    await db.commit()
    return ResponseModel(data={"deleted": item_id})


@router.post("/ensure-annotation", response_model=ResponseModel[LongLeadMaterialOut])
async def ensure_annotation(
    data: EnsureAnnotationRequest,
    current_user: dict = Depends(PermissionChecker("materials.long_lead", "create")),
    db: AsyncSession = Depends(get_db),
):
    """按 material_code + supplier_name 确保注解记录存在，不存在则自动创建"""
    filters = [LongLeadMaterial.material_code == data.material_code]
    if data.supplier_name:
        filters.append(LongLeadMaterial.supplier_name == data.supplier_name)

    result = await db.execute(select(LongLeadMaterial).where(*filters))
    item = result.scalars().first()

    if not item:
        item = LongLeadMaterial(
            material_code=data.material_code,
            supplier_name=data.supplier_name,
            improvement_plan=None,
            status='active',
        )
        db.add(item)
        await db.flush()
        await log_audit(db, "long_lead_material", item.id, "create", field_name="ensure_annotation", operator=current_user["username"])
        await db.commit()
        await db.refresh(item)

    return ResponseModel(data=LongLeadMaterialOut.model_validate(item))


@router.post("/scan", response_model=ResponseModel[dict])
async def scan_long_lead(
    current_user: dict = Depends(PermissionChecker("materials.long_lead", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await scan_and_create_annotations(db)
    await log_audit(db, "long_lead_material", 0, "scan", operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)
