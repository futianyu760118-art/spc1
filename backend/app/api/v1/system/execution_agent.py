"""系统管理 — 执行面智能体管理端点（状态代理 / 配置 / 远程自重启，设计文档 2026-10-15）"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.ai_config import EXECUTION_AGENT_SCOPE, get_scope_config, get_scope_version, save_scope_config

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentConfigIn(BaseModel):
    config: dict


def _admin_headers() -> dict:
    return {"x-admin-token": get_settings().AGENT_ADMIN_TOKEN}


async def _call_agent(path: str, *, timeout: float = 10.0, method: str = "GET") -> dict:
    base = get_settings().EXECUTION_AGENT_BASE_URL.rstrip("/")
    if not base:
        return {"online": False, "reason": "EXECUTION_AGENT_BASE_URL 未配置"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, f"{base}{path}", headers=_admin_headers())
        if resp.status_code == 401:
            return {"online": False, "reason": "admin token 不匹配"}
        resp.raise_for_status()
        return {"online": True, **resp.json()}
    except httpx.HTTPError as e:
        return {"online": False, "reason": f"agent 不可达: {e.__class__.__name__}"}


@router.get("/status", response_model=ResponseModel[dict])
async def agent_status(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    agent = await _call_agent("/admin/status")
    recent = (await db.execute(text(
        "SELECT task_id, task_type, status, llm_called, error_code, duration_ms, created_at "
        "FROM reasoning_task ORDER BY id DESC LIMIT 10"
    ))).mappings().all()
    return {
        "agent": agent,
        "db_version": await get_scope_version(db, EXECUTION_AGENT_SCOPE),
        "config_pending_restart": (
            agent.get("online") and agent.get("configVersion") is not None
            and int(agent["configVersion"]) != await get_scope_version(db, EXECUTION_AGENT_SCOPE)
        ),
        "recent_reasoning_tasks": [dict(r) for r in recent],
    }


@router.get("/config", response_model=ResponseModel[dict])
async def get_agent_config(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    from app.services.ai_config import SCOPE_DEFS
    return {
        "version": await get_scope_version(db, EXECUTION_AGENT_SCOPE),
        "config": await get_scope_config(db, EXECUTION_AGENT_SCOPE),
        "defs": {k: {"label": d.label, "description": d.description} for k, d in SCOPE_DEFS[EXECUTION_AGENT_SCOPE].items()},
    }


@router.put("/config", response_model=ResponseModel[dict])
async def update_agent_config(
    body: AgentConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "update")),
):
    operator = getattr(current_user, "username", None) or str(
        getattr(current_user, "user_id", "") or getattr(current_user, "id", ""))
    try:
        version = await save_scope_config(db, EXECUTION_AGENT_SCOPE, body.config, operator)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"version": version, "message": "已保存；agent 重启后生效"}


@router.post("/restart", response_model=ResponseModel[dict])
async def restart_agent(
    current_user=Depends(PermissionChecker("ai.execution_agent", "update")),
):
    result = await _call_agent("/admin/restart", method="POST", timeout=5.0)
    if not result.get("online"):
        raise HTTPException(status_code=503, detail=f"无法重启：{result.get('reason')}")
    return {"message": "重启指令已下发，容器 restart 策略将自动拉起"}
