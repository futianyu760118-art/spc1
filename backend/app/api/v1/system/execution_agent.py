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
from app.services.ai_config import (
    EXECUTION_AGENT_SCOPE,
    SCOPE_DEFS,
    get_scope_config,
    get_scope_version,
    operator_name,
    save_scope_config,
)

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
            return {"online": False, "reason": "admin token 不匹配（backend 与 agent 容器的 AGENT_ADMIN_TOKEN 不一致）"}
        if resp.status_code == 503:
            try:
                if resp.json().get("status") == "admin_disabled":
                    return {"online": False, "reason": "agent 未配置 AGENT_ADMIN_TOKEN（admin 面禁用）"}
            except ValueError:
                pass
        resp.raise_for_status()
        try:
            body = resp.json()
        except ValueError:
            return {"online": False, "reason": "响应非 JSON"}
        return {"online": True, **body}
    except httpx.HTTPError as e:
        return {"online": False, "reason": f"agent 不可达: {e.__class__.__name__}"}


@router.get("/status", response_model=ResponseModel[dict])
async def agent_status(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    agent = await _call_agent("/admin/status")
    db_version = await get_scope_version(db, EXECUTION_AGENT_SCOPE)
    recent = (await db.execute(text(
        "SELECT task_id, task_type, status, llm_called, error_code, duration_ms, created_at "
        "FROM reasoning_task ORDER BY id DESC LIMIT 10"
    ))).mappings().all()
    config_pending_restart = False
    if agent.get("online") and agent.get("configVersion") is not None:
        try:
            config_pending_restart = int(agent["configVersion"]) != db_version
        except (TypeError, ValueError):
            config_pending_restart = False
    return ResponseModel(data={
        "agent": agent,
        "db_version": db_version,
        "config_pending_restart": config_pending_restart,
        "recent_reasoning_tasks": [dict(r) for r in recent],
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
