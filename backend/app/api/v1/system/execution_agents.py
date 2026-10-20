"""系统管理 — 执行面多智能体管理端点（按 agent_key 隔离，设计文档 2026-10-20）"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.ai_config import (
    SCOPE_DEFS,
    get_scope_config,
    get_scope_version,
    operator_name,
    save_scope_config,
)
from app.services.execution_agents import (
    call_agent_spec,
    fetch_recent_reasoning_tasks,
    get_agent_spec,
    list_agent_statuses,
    summarize_agent_status,
)

router = APIRouter()


class AgentConfigIn(BaseModel):
    config: dict


def _spec_or_404(agent_key: str):
    try:
        return get_agent_spec(agent_key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"未知执行面智能体: {agent_key}")


@router.get("", response_model=ResponseModel[list])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    return ResponseModel(data=await list_agent_statuses(db))


@router.get("/{agent_key}/status", response_model=ResponseModel[dict])
async def agent_status(
    agent_key: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    spec = _spec_or_404(agent_key)
    status = await call_agent_spec(spec, "/admin/status")
    db_version = await get_scope_version(db, spec.scope)
    summary = summarize_agent_status(spec, status, db_version)
    recent = await fetch_recent_reasoning_tasks(db) if spec.supports_recent_reasoning_tasks else []
    return ResponseModel(data={
        "agent": summary,
        "db_version": db_version,
        "config_pending_restart": summary["config_pending_restart"],
        "recent_reasoning_tasks": recent,
    })


@router.get("/{agent_key}/config", response_model=ResponseModel[dict])
async def get_agent_config(
    agent_key: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    spec = _spec_or_404(agent_key)
    return ResponseModel(data={
        "version": await get_scope_version(db, spec.scope),
        "config": await get_scope_config(db, spec.scope),
        "defs": {
            k: {"label": d.label, "description": d.description, "value_type": d.value_type}
            for k, d in SCOPE_DEFS[spec.scope].items()
        },
    })


@router.put("/{agent_key}/config", response_model=ResponseModel[dict])
async def update_agent_config(
    agent_key: str,
    body: AgentConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "update")),
):
    spec = _spec_or_404(agent_key)
    try:
        version = await save_scope_config(db, spec.scope, body.config, operator_name(current_user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResponseModel(message="已保存；agent 重启后生效", data={"version": version})


@router.post("/{agent_key}/restart", response_model=ResponseModel[dict])
async def restart_agent(
    agent_key: str,
    current_user=Depends(PermissionChecker("ai.execution_agent", "update")),
):
    spec = _spec_or_404(agent_key)
    result = await call_agent_spec(spec, "/admin/restart", method="POST", timeout=5.0)
    if not result.get("online"):
        raise HTTPException(status_code=503, detail=f"无法重启：{result.get('reason')}")
    return ResponseModel(message="重启指令已下发，容器 restart 策略将自动拉起")
