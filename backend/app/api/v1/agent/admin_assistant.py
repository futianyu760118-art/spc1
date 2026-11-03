"""智能体中心 — 智能助手监控与配置端点（原 /system/ai-assistant，2026-10-30 迁入）"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
import app.services.assistant.tool_registry  # noqa: F401 — 必须先于 ai_config 导入，避免部分初始化循环
# agent 包是 v1 路由中最先加载的域；若 ai_config 先入口会触发
# ai_config → assistant 包 → execution_agents → ai_config 的部分初始化循环
from app.services.ai_config import (
    ASSISTANT_SCOPE,
    SCOPE_DEFS,
    get_scope_config,
    get_scope_version,
    operator_name,
    save_scope_config,
)

router = APIRouter()


class AssistantConfigIn(BaseModel):
    config: dict


@router.get("/stats", response_model=ResponseModel[dict])
async def assistant_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    since = f"NOW() - INTERVAL '{days} days'"
    total_row = (await db.execute(text(
        f"SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN is_success THEN 1 ELSE 0 END),0) AS ok, "
        f"COALESCE(AVG(duration_ms),0) AS avg_ms, COALESCE(SUM(total_tokens),0) AS tokens, "
        f"COUNT(DISTINCT user_id) AS active_users FROM assistant_run WHERE created_at >= {since}"
    ))).mappings().first()
    trend = (await db.execute(text(
        f"SELECT to_char(created_at,'YYYY-MM-DD') AS day, COUNT(*) AS total, "
        f"SUM(CASE WHEN is_success THEN 1 ELSE 0 END) AS ok "
        f"FROM assistant_run WHERE created_at >= {since} GROUP BY day ORDER BY day"
    ))).mappings().all()
    top_tools = (await db.execute(text(
        f"SELECT tool, COUNT(*) AS hits FROM assistant_run, "
        f"jsonb_array_elements_text(tools_called) AS tool "
        # ORM 写入的 Python None 会落成 jsonb 标量 null（非 SQL NULL），
        # 无 jsonb_typeof 守卫时 jsonb_array_elements_text 遇标量直接报错
        f"WHERE created_at >= {since} AND jsonb_typeof(tools_called) = 'array' "
        f"GROUP BY tool ORDER BY hits DESC LIMIT 10"
    ))).mappings().all()
    return ResponseModel(data={
        "total": total_row["total"],
        "success": total_row["ok"],
        "success_rate": round(total_row["ok"] / total_row["total"], 4) if total_row["total"] else None,
        "avg_duration_ms": round(float(total_row["avg_ms"]), 1),
        "total_tokens": total_row["tokens"],
        "active_users": total_row["active_users"],
        "trend": [dict(r) for r in trend],
        "top_tools": [dict(r) for r in top_tools],
    })


@router.get("/runs", response_model=ResponseModel[dict])
async def assistant_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    intent: Optional[str] = Query(None),
    is_success: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    conds = [f"created_at >= NOW() - INTERVAL '{days} days'"]
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}
    if intent:
        conds.append("intent = :intent")
        params["intent"] = intent
    if is_success is not None:
        conds.append("is_success = :is_success")
        params["is_success"] = is_success
    where = " AND ".join(conds)
    total = (await db.execute(text(f"SELECT COUNT(*) FROM assistant_run WHERE {where}"), params)).scalar()
    rows = (await db.execute(text(
        f"SELECT id, trace_id, session_id, user_id, user_message, intent, tools_called, "
        f"tool_rounds, total_tokens, duration_ms, is_success, error_message, created_at "
        f"FROM assistant_run WHERE {where} ORDER BY id DESC LIMIT :limit OFFSET :offset"
    ), params)).mappings().all()
    return ResponseModel(data={"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]})


@router.get("/config", response_model=ResponseModel[dict])
async def get_assistant_config(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    from app.services.assistant.agent import INTENT_RECOGNITION_PROMPT
    from app.services.assistant.orchestrator import SYSTEM_PROMPT
    from app.core.config import get_settings

    config = await get_scope_config(db, ASSISTANT_SCOPE)
    config["system_prompt"] = config["system_prompt"] or SYSTEM_PROMPT
    config["intent_prompt"] = config["intent_prompt"] or INTENT_RECOGNITION_PROMPT
    config["model_name"] = config["model_name"] or get_settings().AI_OPENAI_MODEL
    return ResponseModel(data={
        "version": await get_scope_version(db, ASSISTANT_SCOPE),
        "config": config,
        "defs": {k: {"label": d.label, "description": d.description} for k, d in SCOPE_DEFS[ASSISTANT_SCOPE].items()},
    })


@router.put("/config", response_model=ResponseModel[dict])
async def update_assistant_config(
    body: AssistantConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        version = await save_scope_config(db, ASSISTANT_SCOPE, body.config, operator_name(current_user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResponseModel(data={"version": version})
