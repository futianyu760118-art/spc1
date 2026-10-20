"""智能助手 API 路由 — Agent + SSE 流式 + 日志查询"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.security import PermissionChecker
from app.models.basicdata.ai_agent import AssistantRun
from app.schemas.assistant.schemas import ChatMessageIn, AssistantReply, ToolInfo

import app.services.assistant.tools  # noqa: F401
from app.services.assistant import agent
from app.services.assistant import agent_stream
from app.services.assistant.tool_registry import get_all_tools
from app.services.assistant import session_store
from app.services.assistant.run_logger import list_log_files, read_log_file
from app.services.assistant.cancellation import CancellationRegistry
from app.services.assistant.hub_reporter import now_iso, report_assistant_event

logger = logging.getLogger(__name__)

router = APIRouter()


def _report_turn_start(session_id: str, user_id: str, message: str, is_new_session: bool) -> None:
    """会话级观测上报（traceId=会话 ID）：新会话发 conversation_started，每次对话发 message（仅摘要）"""
    if is_new_session:
        report_assistant_event(
            session_id, "conversation_started", "会话开始", "info",
            f"用户 {user_id} 发起会话" if user_id else "发起会话",
            {"userId": user_id}, started_at=now_iso(),
        )
    report_assistant_event(
        session_id, "message", "用户消息", "info",
        f"用户询问：{message[:80]}",
        {"length": len(message)}, started_at=now_iso(),
    )


async def _record_run(
    *,
    trace_id: str,
    session_id: str,
    user_id: str,
    message: str,
    intent: Optional[str],
    tools_called: list,
    tool_rounds: Optional[int],
    total_tokens: Optional[int],
    duration_ms: Optional[float],
    is_success: bool,
    error_message: Optional[str],
) -> None:
    """用量审计落库；失败仅告警不影响对话主流程。

    独立 session + 显式 commit：StreamingResponse 的 body generator 在 get_db 的
    teardown(commit) 之后才被 Starlette 迭代，借请求级 session 写入的行会随隐式回滚丢失。
    """
    intent = (intent or "").lower() or None
    try:
        async with AsyncSessionLocal() as session:
            session.add(AssistantRun(
                trace_id=trace_id or "",
                session_id=session_id or None,
                user_id=user_id or None,
                user_message=(message or "")[:500],
                intent=intent,
                tools_called=tools_called or None,
                tool_rounds=tool_rounds,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
                is_success=is_success,
                error_message=error_message,
            ))
            await session.commit()
    except Exception as exc:
        logger.warning(f"[assistant] 用量落库失败 trace={trace_id}: {exc}")


def _current_user_id(current_user: Any) -> str:
    """PermissionChecker 返回 dict（JWT payload），user id 在 sub/user_id 键"""
    user_id = current_user.get("sub") or current_user.get("user_id") or ""
    return str(user_id)


def _diag_tools(diagnostics: Optional[dict]) -> list:
    if not diagnostics:
        return []
    names: list = []
    for item in diagnostics.get("tools") or []:
        name = item.get("name")
        if name and name not in names:
            names.append(name)
    return names


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
    user_id = _current_user_id(current_user)

    _report_turn_start(session_id, user_id, body.message, is_new_session=not body.session_id)

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

        disconnect_task = asyncio.create_task(_watch_disconnect())

    try:
        try:
            reply = await agent.run(
                message=body.message,
                db=db,
                session_id=session_id,
                conversation_history=body.conversation_history,
                trace_id=trace_id,
                user_id=str(user_id) if user_id else "",
            )
        except Exception as e:
            await _record_run(
                trace_id=trace_id, session_id=session_id, user_id=str(user_id), message=body.message,
                intent=None, tools_called=[], tool_rounds=None, total_tokens=None,
                duration_ms=round((time.perf_counter() - request_start) * 1000, 2),
                is_success=False, error_message=str(e),
            )
            report_assistant_event(
                session_id, "error", "助手异常", "failed", str(e)[:200], started_at=now_iso(),
            )
            raise

        total_duration_ms = round((time.perf_counter() - request_start) * 1000, 2)
        if reply.diagnostics:
            reply.diagnostics["total_duration_ms"] = total_duration_ms
        reply.session_id = session_id
        reply.trace_id = trace_id
        errors = (reply.diagnostics or {}).get("errors") or []
        await _record_run(
            trace_id=trace_id, session_id=session_id, user_id=str(user_id), message=body.message,
            intent=(reply.diagnostics or {}).get("intent"),
            tools_called=_diag_tools(reply.diagnostics),
            tool_rounds=len((reply.diagnostics or {}).get("llm_rounds") or []),
            total_tokens=(reply.diagnostics or {}).get("total_tokens"),
            duration_ms=total_duration_ms,
            is_success=not errors,
            error_message=errors[0].get("message") if errors else None,
        )
        for err in errors:
            report_assistant_event(
                session_id, "error", "助手异常", "failed",
                str(err.get("message", ""))[:200], started_at=now_iso(),
            )
        report_assistant_event(
            session_id, "assistant_reply", "助手回复", "completed",
            f"回复：{(reply.text or '')[:80]}",
            {"intent": reply.intent, "length": len(reply.text or "")},
            started_at=now_iso(), duration_ms=total_duration_ms,
        )
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
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """SSE 流式对话接口。

    不用 get_db 依赖 session：FastAPI 在发送响应体之前就退出依赖上下文，
    generator 里再拿已关闭的 session 会重开事务且无人回收（连接池泄漏）。
    改为在 generator 内自建 session，随生成器关闭释放。
    """
    trace_id = str(uuid.uuid4())
    session_id = body.session_id or str(uuid.uuid4())
    user_id = _current_user_id(current_user)

    _report_turn_start(session_id, user_id, body.message, is_new_session=not body.session_id)

    async def event_generator():
        started = time.perf_counter()
        run_info: Dict[str, Any] = {"tools": [], "stats": None, "intent": None, "error": None, "done": False, "text": ""}

        def _track(raw_event: str) -> None:
            lines = raw_event.split("\n")
            event_name = next((l[7:] for l in lines if l.startswith("event: ")), "")
            data_line = next((l[6:] for l in lines if l.startswith("data: ")), None)
            if not data_line:
                return
            try:
                payload = json.loads(data_line)
            except Exception:
                return
            if event_name == "tool_start":
                name = payload.get("name")
                if name and name not in run_info["tools"]:
                    run_info["tools"].append(name)
            elif event_name == "done":
                run_info["done"] = True
                run_info["intent"] = payload.get("intent")
                run_info["stats"] = payload.get("stats")
            elif event_name == "delta":
                run_info["text"] += payload.get("text") or ""
            elif event_name == "error":
                run_info["error"] = payload.get("message")

        try:
            yield f"event: session\ndata: {json.dumps({'session_id': session_id, 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
            async with AsyncSessionLocal() as stream_db:
                async for event in agent_stream.run_stream(
                    message=body.message,
                    db=stream_db,
                    session_id=session_id,
                    conversation_history=body.conversation_history,
                    trace_id=trace_id,
                    user_id=str(user_id) if user_id else "",
                    request=request,
                ):
                    _track(event)
                    yield event
        finally:
            stats = run_info["stats"] or {}
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            # shield：生成器被二次取消（客户端断开）时保证落库任务不被连带取消
            await asyncio.shield(_record_run(
                trace_id=trace_id, session_id=session_id, user_id=str(user_id), message=body.message,
                intent=run_info["intent"],
                tools_called=run_info["tools"],
                tool_rounds=stats.get("tool_rounds"),
                total_tokens=stats.get("total_tokens"),
                duration_ms=duration_ms,
                is_success=run_info["done"] and not run_info["error"],
                error_message=run_info["error"] or (None if run_info["done"] else "stream_interrupted"),
            ))
            if run_info["error"]:
                report_assistant_event(
                    session_id, "error", "助手异常", "failed",
                    str(run_info["error"])[:200], started_at=now_iso(),
                )
            if run_info["done"] and run_info["text"]:
                report_assistant_event(
                    session_id, "assistant_reply", "助手回复", "completed",
                    f"回复：{run_info['text'][:80]}",
                    {"intent": run_info["intent"], "length": len(run_info["text"])},
                    started_at=now_iso(), duration_ms=duration_ms,
                )

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
    report_assistant_event(session_id, "conversation_ended", "会话结束", "info", "用户清空会话", started_at=now_iso())
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
