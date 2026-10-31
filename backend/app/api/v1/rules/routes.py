from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.rules.risk_rule import RiskRule
from app.schemas.common import ResponseModel
from app.schemas.exception.schemas import RiskRuleOut, RiskRuleCreate, RiskRuleUpdate

router = APIRouter()


@router.get("", response_model=ResponseModel[list[RiskRuleOut]])
async def list_rules(
    current_user: dict = Depends(PermissionChecker("rules.risk_rules", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RiskRule).order_by(RiskRule.rule_type, RiskRule.rule_code))
    items = [RiskRuleOut.model_validate(row) for row in result.scalars().all()]
    return ResponseModel(data=items)


@router.post("", response_model=ResponseModel[RiskRuleOut])
async def create_rule(
    data: RiskRuleCreate,
    current_user: dict = Depends(PermissionChecker("rules.risk_rules", "create")),
    db: AsyncSession = Depends(get_db),
):
    rule = RiskRule(**data.model_dump(), created_by=current_user["username"])
    db.add(rule)
    await db.flush()
    await log_audit(db, "risk_rule", rule.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(rule)
    return ResponseModel(data=RiskRuleOut.model_validate(rule))


@router.put("/{rule_id}", response_model=ResponseModel[RiskRuleOut])
async def update_rule(
    rule_id: int,
    data: RiskRuleUpdate,
    current_user: dict = Depends(PermissionChecker("rules.risk_rules", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RiskRule).where(RiskRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "risk_rule", rule.id, "update", old_obj=rule, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(rule, field, value)
    rule.version += 1
    await db.commit()
    await db.refresh(rule)
    return ResponseModel(data=RiskRuleOut.model_validate(rule))
