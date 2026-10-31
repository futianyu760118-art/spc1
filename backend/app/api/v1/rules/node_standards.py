"""规则配置中心 — 节点标准 API"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.rules.node_standard import NodeStandard
from app.schemas.common import ResponseModel
from app.schemas.rules.schemas import NodeStandardOut, NodeStandardCreate, NodeStandardUpdate

router = APIRouter()


@router.get("", response_model=ResponseModel[list[NodeStandardOut]])
async def list_node_standards(
    applicable_scene: str | None = None,
    current_user: dict = Depends(PermissionChecker("rules.node_standards", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NodeStandard).order_by(NodeStandard.node_code)
    if applicable_scene:
        stmt = stmt.where(NodeStandard.applicable_scene == applicable_scene)
    result = await db.execute(stmt)
    items = [NodeStandardOut.model_validate(row) for row in result.scalars().all()]
    return ResponseModel(data=items)


@router.post("", response_model=ResponseModel[NodeStandardOut])
async def create_node_standard(
    data: NodeStandardCreate,
    current_user: dict = Depends(PermissionChecker("rules.node_standards", "create")),
    db: AsyncSession = Depends(get_db),
):
    ns = NodeStandard(**data.model_dump(), created_by=current_user["username"])
    db.add(ns)
    await db.flush()
    await log_audit(db, "node_standard", ns.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(ns)
    return ResponseModel(data=NodeStandardOut.model_validate(ns))


@router.put("/{standard_id}", response_model=ResponseModel[NodeStandardOut])
async def update_node_standard(
    standard_id: int,
    data: NodeStandardUpdate,
    current_user: dict = Depends(PermissionChecker("rules.node_standards", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(NodeStandard).where(NodeStandard.id == standard_id))
    ns = result.scalar_one_or_none()
    if not ns:
        raise HTTPException(status_code=404, detail="节点标准不存在")
    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "node_standard", ns.id, "update", old_obj=ns, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(ns, field, value)
    await db.commit()
    await db.refresh(ns)
    return ResponseModel(data=NodeStandardOut.model_validate(ns))


@router.delete("/{standard_id}", response_model=ResponseModel)
async def delete_node_standard(
    standard_id: int,
    current_user: dict = Depends(PermissionChecker("rules.node_standards", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(NodeStandard).where(NodeStandard.id == standard_id))
    ns = result.scalar_one_or_none()
    if not ns:
        raise HTTPException(status_code=404, detail="节点标准不存在")
    await log_audit(db, "node_standard", ns.id, "delete", operator=current_user["username"])
    await db.delete(ns)
    await db.commit()
    return ResponseModel(data=None, message="删除成功")
