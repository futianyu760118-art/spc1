"""智能助手 API 路由 — 单层 Agent + 直接 Tool Calling + SSE 流式输出"""

import uuid
import logging
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.assistant.schemas import ChatMessageIn, AssistantReply, ToolInfo

# 导入 tools 以触发注册
import app.services.assistant.tools  # noqa: F401
from app.services.assistant import agent
from app.services.assistant import agent_stream
from app.services.assistant.tool_registry import get_all_tools
from app.services.assistant import session_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=dict)
async def chat(
    body: ChatMessageIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """接收用户消息，运行 Agent"""
    trace_id = str(uuid.uuid4())
    request_start = time.perf_counter()

    reply = await agent.run(
        message=body.message,
        db=db,
        session_id=body.session_id or "",
        conversation_history=body.conversation_history,
        trace_id=trace_id,
    )

    # 计算总耗时
    total_duration_ms = round((time.perf_counter() - request_start) * 1000, 2)
    if reply.diagnostics:
        reply.diagnostics["total_duration_ms"] = total_duration_ms

    reply.session_id = body.session_id or str(uuid.uuid4())
    reply.trace_id = trace_id
    return {"code": 0, "data": reply.model_dump()}


@router.post("/chat/stream")
async def chat_stream(
    body: ChatMessageIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """SSE 流式对话接口"""
    trace_id = str(uuid.uuid4())
    session_id = body.session_id or str(uuid.uuid4())

    async def event_generator():
        """生成 SSE 事件流"""
        import json

        # 先发送 session_id
        yield f"event: session\ndata: {json.dumps({'session_id': session_id, 'trace_id': trace_id})}\n\n"

        async for event in agent_stream.run_stream(
            message=body.message,
            db=db,
            session_id=session_id,
            conversation_history=body.conversation_history,
            trace_id=trace_id,
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
