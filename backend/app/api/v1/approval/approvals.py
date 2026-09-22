"""审批中心 - 统一待我审批 / 审批配置 API。

待审批列表由 approval_registry 注册的各业务流程 provider 聚合而成（新流程只需注册）；
审批链配置只允许操作「已注册」的 biz_type，避免与其它模块的配置页产生双写路径。
"""

import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.common import approval_providers  # noqa: F401 — 导入即触发各业务流程注册
from app.services.common.approval_registry import get_pending_providers, is_registered

router = APIRouter()


@router.get("/pending", response_model=ResponseModel)
async def list_pending_approvals(
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.pending", "read")),
    db: AsyncSession = Depends(get_db),
):
    """聚合全部已注册流程的待我审批条目，各 biz 内部已按审批节点权限过滤（admin 全量）。"""
    items: list[dict] = []
    for provider in get_pending_providers():
        items.extend(await provider.fetch(db, current_user["username"], current_user["role"]))
    items.sort(key=lambda x: x.get("submitted_at") or "", reverse=True)
    return ResponseModel(data=items)


@router.get("/configs", response_model=ResponseModel)
async def list_approval_configs(
    _: dict = Depends(PermissionChecker("approval.config", "read")),
    db: AsyncSession = Depends(get_db),
):
    """审批链列表：已注册的业务流程 ∪（其）approval_config 配置行。"""
    rows = await db.execute(text(
        "SELECT biz_type, biz_name, nodes, is_active, updated_by, updated_at FROM approval_config"
    ))
    existing: dict[str, dict] = {}
    for r in rows:
        d = dict(r._mapping)
        if isinstance(d.get("nodes"), str):
            d["nodes"] = json.loads(d.get("nodes") or "[]")
        if isinstance(d.get("updated_at"), datetime):
            d["updated_at"] = d["updated_at"].isoformat()
        existing[d["biz_type"]] = d

    items = []
    for provider in get_pending_providers():
        items.append(existing.pop(provider.biz_type, {
            "biz_type": provider.biz_type, "biz_name": provider.biz_name,
            "nodes": [], "is_active": True, "updated_by": None, "updated_at": None,
        }))
    return ResponseModel(data={"items": items})


@router.get("/configs/{biz_type}", response_model=ResponseModel)
async def get_approval_config(
    biz_type: str,
    _: dict = Depends(PermissionChecker("approval.config", "read")),
    db: AsyncSession = Depends(get_db),
):
    if not is_registered(biz_type):
        return ResponseModel(code=1, message="该业务流程未接入审批中心")
    row = await db.execute(text(
        "SELECT biz_type, biz_name, nodes, is_active, updated_by, updated_at FROM approval_config WHERE biz_type = :bt LIMIT 1"
    ), {"bt": biz_type})
    r = row.fetchone()
    if not r:
        return ResponseModel(data={"biz_type": biz_type, "nodes": []})
    d = dict(r._mapping)
    if isinstance(d.get("nodes"), str):
        d["nodes"] = json.loads(d.get("nodes") or "[]")
    if isinstance(d.get("updated_at"), datetime):
        d["updated_at"] = d["updated_at"].isoformat()
    return ResponseModel(data=d)


@router.put("/configs/{biz_type}", response_model=ResponseModel)
async def save_approval_config(
    biz_type: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(PermissionChecker("approval.config", "update")),
    db: AsyncSession = Depends(get_db),
):
    if not is_registered(biz_type):
        return ResponseModel(code=1, message="该业务流程未接入审批中心")
    nodes = data.get("nodes", [])
    provider = next((p for p in get_pending_providers() if p.biz_type == biz_type), None)
    biz_name = data.get("biz_name") or (provider.biz_name if provider else biz_type)
    row = await db.execute(text("SELECT id FROM approval_config WHERE biz_type = :bt LIMIT 1"), {"bt": biz_type})
    if row.fetchone():
        await db.execute(text("""
            UPDATE approval_config SET biz_name = :bn, nodes = :nodes, is_active = TRUE,
                                       updated_by = :ub, updated_at = NOW()
            WHERE biz_type = :bt
        """), {"bn": biz_name, "nodes": json.dumps(nodes), "ub": current_user["username"], "bt": biz_type})
    else:
        await db.execute(text("""
            INSERT INTO approval_config (biz_type, biz_name, nodes, is_active, updated_by)
            VALUES (:bt, :bn, :nodes, TRUE, :ub)
        """), {"bt": biz_type, "bn": biz_name, "nodes": json.dumps(nodes), "ub": current_user["username"]})
    await db.commit()
    return ResponseModel(data={"biz_type": biz_type, "nodes": nodes}, message="保存成功")


@router.get("/roles", response_model=ResponseModel)
async def list_role_options(
    _: dict = Depends(PermissionChecker("approval.config", "read")),
    db: AsyncSession = Depends(get_db),
):
    """审批链编辑器角色下拉数据源（审批域自有权限，不依赖「角色管理」读权限）。"""
    rows = await db.execute(text("SELECT role_code, role_name FROM sys_role ORDER BY id"))
    return ResponseModel(data={"items": [{"role_code": r[0], "role_name": r[1]} for r in rows]})
