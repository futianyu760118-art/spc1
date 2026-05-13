"""规则配置中心 — 点检规则 API"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.rules.inspection_rule import InspectionRule
from app.schemas.common import ResponseModel
from app.schemas.rules.schemas import InspectionRuleOut, InspectionRuleCreate, InspectionRuleUpdate

router = APIRouter()


@router.get("", response_model=ResponseModel[list[InspectionRuleOut]])
async def list_inspection_rules(
    module_code: str | None = None,
    current_user: dict = Depends(PermissionChecker("rules.inspection", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(InspectionRule).order_by(InspectionRule.sort_order, InspectionRule.item_code)
    if module_code:
        stmt = stmt.where(InspectionRule.module_code == module_code)
    result = await db.execute(stmt)
    items = [InspectionRuleOut.model_validate(row) for row in result.scalars().all()]
    return ResponseModel(data=items)


@router.post("", response_model=ResponseModel[InspectionRuleOut])
async def create_inspection_rule(
    data: InspectionRuleCreate,
    current_user: dict = Depends(PermissionChecker("rules.inspection", "create")),
    db: AsyncSession = Depends(get_db),
):
    rule = InspectionRule(**data.model_dump(), created_by=current_user["username"])
    db.add(rule)
    await db.flush()
    await log_audit(db, "inspection_rule", rule.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(rule)
    return ResponseModel(data=InspectionRuleOut.model_validate(rule))


@router.put("/{rule_id}", response_model=ResponseModel[InspectionRuleOut])
async def update_inspection_rule(
    rule_id: int,
    data: InspectionRuleUpdate,
    current_user: dict = Depends(PermissionChecker("rules.inspection", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InspectionRule).where(InspectionRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="点检规则不存在")
    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "inspection_rule", rule.id, "update", old_obj=rule, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return ResponseModel(data=InspectionRuleOut.model_validate(rule))


@router.delete("/{rule_id}", response_model=ResponseModel)
async def delete_inspection_rule(
    rule_id: int,
    current_user: dict = Depends(PermissionChecker("rules.inspection", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InspectionRule).where(InspectionRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="点检规则不存在")
    await log_audit(db, "inspection_rule", rule.id, "delete", operator=current_user["username"])
    await db.delete(rule)
    await db.commit()
    return ResponseModel(data=None, message="删除成功")
