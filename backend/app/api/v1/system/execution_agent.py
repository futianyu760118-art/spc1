"""系统管理 — 执行面智能体管理端点（状态代理 / 配置 / 远程自重启，设计文档 2026-10-15）
(legacy，单 Agent；多智能体见 execution_agents.py)"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.ai_config import (
    EXECUTION_AGENT_SCOPE,
    SCOPE_DEFS,
    get_scope_config,
    get_scope_version,
    operator_name,
    save_scope_config,
)
from app.services.execution_agents import (
    call_agent,
    config_pending_restart,
    fetch_recent_reasoning_tasks,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentConfigIn(BaseModel):
    config: dict


async def _call_agent(path: str, *, timeout: float = 10.0, method: str = "GET") -> dict:
    base = get_settings().EXECUTION_AGENT_BASE_URL.rstrip("/")
    if not base:
        return {"online": False, "reason": "EXECUTION_AGENT_BASE_URL 未配置"}
    return await call_agent(base, path, timeout=timeout, method=method)


@router.get("/status", response_model=ResponseModel[dict])
async def agent_status(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    agent = await _call_agent("/admin/status")
    db_version = await get_scope_version(db, EXECUTION_AGENT_SCOPE)
    recent = await fetch_recent_reasoning_tasks(db)
    return ResponseModel(data={
        "agent": agent,
        "db_version": db_version,
        "config_pending_restart": config_pending_restart(agent, db_version),
        "recent_reasoning_tasks": recent,
    })


@router.get("/config", response_model=ResponseModel[dict])
async def get_agent_config(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    return ResponseModel(data={
        "version": await get_scope_version(db, EXECUTION_AGENT_SCOPE),
        "config": await get_scope_config(db, EXECUTION_AGENT_SCOPE),
        "defs": {k: {"label": d.label, "description": d.description} for k, d in SCOPE_DEFS[EXECUTION_AGENT_SCOPE].items()},
    })


@router.put("/config", response_model=ResponseModel[dict])
async def update_agent_config(
    body: AgentConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "update")),
):
    try:
        version = await save_scope_config(db, EXECUTION_AGENT_SCOPE, body.config, operator_name(current_user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResponseModel(message="已保存；agent 重启后生效", data={"version": version})


@router.post("/restart", response_model=ResponseModel[dict])
async def restart_agent(
    current_user=Depends(PermissionChecker("ai.execution_agent", "update")),
):
    result = await _call_agent("/admin/restart", method="POST", timeout=5.0)
    if not result.get("online"):
        raise HTTPException(status_code=503, detail=f"无法重启：{result.get('reason')}")
    return ResponseModel(message="重启指令已下发，容器 restart 策略将自动拉起")
