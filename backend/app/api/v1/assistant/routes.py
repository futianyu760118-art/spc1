"""智能助手 API 路由 — Agent + SSE 流式 + 日志查询"""

import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.assistant.schemas import ChatMessageIn, AssistantReply, ToolInfo

import app.services.assistant.tools  # noqa: F401
from app.services.assistant import agent
from app.services.assistant import agent_stream
from app.services.assistant.tool_registry import get_all_tools
from app.services.assistant import session_store
from app.services.assistant.run_logger import list_log_files, read_log_file
from app.services.assistant.cancellation import CancellationRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=dict)
async def chat(
    body: ChatMessageIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """接收用户消息，运行 Agent"""
    trace_id = str(uuid.uuid4())
    session_id = body.session_id or str(uuid.uuid4())
    user_id = getattr(current_user, "user_id", "") or getattr(current_user, "id", "")
    if hasattr(user_id, "__int__"):
        user_id = str(user_id)

    request_start = time.perf_counter()

    if session_id:
        await CancellationRegistry.get_or_create(session_id)

    disconnect_task: Optional[Any] = None
    if session_id:

        async def _watch_disconnect():
            try:
                while True:
                    if await request.is_disconnected():
                        CancellationRegistry.trigger(session_id, "client_disconnected")
                        return
                    await asyncio.sleep(0.5)
            except Exception:
                pass

        import asyncio
        disconnect_task = asyncio.create_task(_watch_disconnect())

    try:
        reply = await agent.run(
            message=body.message,
            db=db,
            session_id=session_id,
            conversation_history=body.conversation_history,
            trace_id=trace_id,
            user_id=str(user_id) if user_id else "",
        )

        total_duration_ms = round((time.perf_counter() - request_start) * 1000, 2)
        if reply.diagnostics:
            reply.diagnostics["total_duration_ms"] = total_duration_ms
        reply.session_id = session_id
        reply.trace_id = trace_id
        return {"code": 0, "data": reply.model_dump()}
    finally:
        if disconnect_task is not None:
            disconnect_task.cancel()
        if session_id:
            CancellationRegistry.cleanup(session_id)


@router.post("/chat/stream")
async def chat_stream(
    body: ChatMessageIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """SSE 流式对话接口"""
    trace_id = str(uuid.uuid4())
    session_id = body.session_id or str(uuid.uuid4())
    user_id = getattr(current_user, "user_id", "") or getattr(current_user, "id", "")
    if hasattr(user_id, "__int__"):
        user_id = str(user_id)

    async def event_generator():
        yield f"event: session\ndata: {json.dumps({'session_id': session_id, 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
        async for event in agent_stream.run_stream(
            message=body.message,
            db=db,
            session_id=session_id,
            conversation_history=body.conversation_history,
            trace_id=trace_id,
            user_id=str(user_id) if user_id else "",
            request=request,
        ):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tools", response_model=dict)
async def list_tools(current_user=Depends(PermissionChecker("topbar.ai_search", "read"))):
    """返回当前注册的工具清单"""
    tools = get_all_tools()
    tool_items = [
        ToolInfo(name=t.name, description=t.description)
        for t in tools
    ]
    return {"code": 0, "data": [t.model_dump() for t in tool_items]}


@router.get("/skills", response_model=dict)
async def list_skills(current_user=Depends(PermissionChecker("topbar.ai_search", "read"))):
    """兼容旧接口：返回工具清单（以 skill 格式）"""
    tools = get_all_tools()
    skill_items = [
        {
            "intent": t.name,
            "name": t.display_name or t.name,
            "description": t.description,
            "keywords": t.keywords or [t.name],
            "category": t.category,
        }
        for t in tools
    ]
    return {"code": 0, "data": skill_items}


@router.delete("/sessions/{session_id}")
async def clear_session(
    session_id: str,
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """清除会话历史"""
    await session_store.clear_session(session_id)
    return {"code": 0, "message": "会话已清除"}


@router.get("/logs", response_model=dict)
async def list_logs(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD"),
    session_id: Optional[str] = Query(None, description="会话 ID"),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """列出 Agent 运行日志文件"""
    files = list_log_files(date=date, session_id=session_id)
    items = [
        {
            "trace_id": fp.stem,
            "date": fp.parent.name,
            "path": str(fp),
            "size": fp.stat().st_size,
        }
        for fp in files
    ]
    return {"code": 0, "data": items}


@router.get("/logs/{trace_id}", response_model=dict)
async def get_log(
    trace_id: str,
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """读取指定 trace_id 的 Agent 运行日志（JSONL 全量）"""
    files = list_log_files()
    matched = [fp for fp in files if fp.stem == trace_id]
    if not matched:
        return {"code": 404, "message": f"未找到 trace_id={trace_id} 的日志"}

    fp = matched[0]
    records = read_log_file(fp)
    return {
        "code": 0,
        "data": {
            "trace_id": trace_id,
            "date": fp.parent.name,
            "path": str(fp),
            "records": records,
        },
    }
