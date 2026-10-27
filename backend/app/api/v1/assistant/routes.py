"""智能助手 API 路由 — Agent + SSE 流式 + 日志查询"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.security import PermissionChecker
from app.models.basicdata.ai_agent import AssistantRun
from app.models.basicdata.user import SysUser
from app.schemas.assistant.schemas import ChatMessageIn, AssistantReply, ToolInfo
from app.services.agent import conversation as agent_conversation
from app.services.agent import task_tools
from app.services.agent.context import load_agent_context
from app.services.agent.task_service import TaskError, build_task_context

import app.services.assistant.agent_tools  # noqa: F401 — 触发智能体工具注册
from app.services.assistant import agent
from app.services.assistant import agent_stream
from app.services.assistant import orchestrator
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
    agent_id: Optional[int] = None,
    task_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    trigger: str = "chat",
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
                agent_id=agent_id,
                task_id=task_id,
                conversation_id=conversation_id,
                trigger=trigger,
            ))
            await session.commit()
    except Exception as exc:
        logger.warning(f"[assistant] 用量落库失败 trace={trace_id}: {exc}")


def _current_user_id(current_user: Any) -> str:
    """PermissionChecker 返回 dict（JWT payload），user id 在 sub/user_id 键"""
    user_id = current_user.get("sub") or current_user.get("user_id") or ""
    return str(user_id)


async def _prepare_agent_chat(
    db: AsyncSession,
    user_id: str,
    body: ChatMessageIn,
):
    """构建 AgentContext / 持久化会话 / 任务上下文；功能关闭时返回 None。"""
    if not get_settings().AGENT_TASK_ENABLED:
        return None
    user = await db.get(SysUser, int(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    ctx = await load_agent_context(db, user)
    if ctx.agent.status != "active":
        raise HTTPException(status_code=403, detail="智能体已禁用，请联系管理员启用")
    # 旧客户端仍传 session_id：保留原会话语义，但把会话键绑定到 user+agent，避免跨用户读取。
    if not body.conversation_id and body.session_id and not body.task_id:
        prefix = f"{user.id}:{ctx.agent.id}:"
        session_id = body.session_id
        if not session_id.startswith(prefix):
            session_id = f"{prefix}{session_id}"
        return ctx, None, session_id, body.conversation_history, ""
    try:
        conversation = await agent_conversation.resolve_conversation(
            db,
            agent=ctx.agent,
            user_id=user.id,
            conversation_id=body.conversation_id,
            task_id=body.task_id,
        )
    except agent_conversation.ConversationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    task_context_text = ""
    if body.task_id:
        try:
            task_context_text = await build_task_context(db, body.task_id, user.id)
        except TaskError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message)
    history = body.conversation_history
    if not history:
        history = await agent_conversation.load_recent_messages(db, conversation.id, limit=20)
    session_id = f"{user.id}:{ctx.agent.id}:{conversation.id}"
    return ctx, conversation, session_id, history, task_context_text


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
    user_id = _current_user_id(current_user)
    request_start = time.perf_counter()

    prepared = await _prepare_agent_chat(db, user_id, body)
    ctx = conversation = None
    task_context_text = ""
    if prepared:
        ctx, conversation, session_id, history, task_context_text = prepared
        if conversation:
            await agent_conversation.append_message(
                db, conversation, role="user", content=body.message, trace_id=trace_id,
            )
    else:
        session_id = body.session_id or str(uuid.uuid4())
        history = body.conversation_history

    _report_turn_start(session_id, user_id, body.message, is_new_session=not body.session_id)
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
                conversation_history=history,
                trace_id=trace_id,
                user_id=str(user_id) if user_id else "",
                agent_context=ctx,
                agent_task_id=body.task_id,
                conversation_id=conversation.id if conversation else None,
                task_context_text=task_context_text,
            )
        except Exception as e:
            if conversation:
                await agent_conversation.append_message(
                    db, conversation, role="assistant",
                    content=f"处理失败：{str(e)[:500]}", trace_id=trace_id,
                )
            await _record_run(
                trace_id=trace_id, session_id=session_id, user_id=str(user_id), message=body.message,
                intent=None, tools_called=[], tool_rounds=None, total_tokens=None,
                duration_ms=round((time.perf_counter() - request_start) * 1000, 2),
                is_success=False, error_message=str(e),
                agent_id=ctx.agent.id if ctx else None,
                task_id=body.task_id,
                conversation_id=conversation.id if conversation else None,
                trigger="task_chat" if body.task_id else "chat",
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
        if conversation:
            reply.conversation_id = conversation.id
            await agent_conversation.append_message(
                db, conversation, role="assistant", content=reply.text,
                tool_calls=[
                    {"tool": step.tool, "status": step.status, "summary": step.summary}
                    for step in (reply.steps or [])
                ] or None,
                token_usage={"total_tokens": (reply.diagnostics or {}).get("total_tokens")},
                trace_id=trace_id,
            )
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
            agent_id=ctx.agent.id if ctx else None,
            task_id=body.task_id,
            conversation_id=conversation.id if conversation else None,
            trigger="task_chat" if body.task_id else "chat",
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
    user_id = _current_user_id(current_user)

    async def event_generator():
        started = time.perf_counter()
        run_info: Dict[str, Any] = {
            "tools": [], "stats": None, "intent": None, "error": None,
            "done": False, "text": "", "steps": [],
            "agent_id": None, "conversation_id": None,
        }
        session_id = body.session_id or str(uuid.uuid4())

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
            if event_name == "step_started":
                name = payload.get("step", {}).get("tool")
                if name and name not in run_info["tools"]:
                    run_info["tools"].append(name)
            elif event_name == "done":
                run_info["done"] = True
                run_info["intent"] = payload.get("intent")
                run_info["stats"] = payload.get("stats")
                run_info["steps"] = payload.get("steps") or []
            elif event_name == "delta":
                run_info["text"] += payload.get("text") or ""
            elif event_name == "error":
                run_info["error"] = payload.get("message")

        try:
            async with AsyncSessionLocal() as stream_db:
                try:
                    prepared = await _prepare_agent_chat(stream_db, user_id, body)
                except HTTPException as exc:
                    yield f"event: error\ndata: {json.dumps({'message': exc.detail}, ensure_ascii=False)}\n\n"
                    return
                ctx = conversation = None
                history = body.conversation_history
                task_context_text = ""
                if prepared:
                    ctx, conversation, session_id, history, task_context_text = prepared
                    run_info["agent_id"] = ctx.agent.id
                    if conversation:
                        run_info["conversation_id"] = conversation.id
                        await agent_conversation.append_message(
                            stream_db, conversation, role="user", content=body.message, trace_id=trace_id,
                        )
                        await stream_db.commit()
                _report_turn_start(
                    session_id, user_id, body.message, is_new_session=not body.session_id,
                )
                yield f"event: session\ndata: {json.dumps({'session_id': session_id, 'trace_id': trace_id, 'conversation_id': run_info['conversation_id']}, ensure_ascii=False)}\n\n"
                try:
                    async for event in agent_stream.run_stream(
                        message=body.message,
                        db=stream_db,
                        session_id=session_id,
                        conversation_history=history,
                        trace_id=trace_id,
                        user_id=str(user_id) if user_id else "",
                        request=request,
                        agent_context=ctx,
                        agent_task_id=body.task_id,
                        conversation_id=conversation.id if conversation else None,
                        task_context_text=task_context_text,
                    ):
                        _track(event)
                        yield event
                finally:
                    if conversation:
                        content = run_info["text"] or (
                            f"处理失败：{run_info['error'][:500]}" if run_info["error"] else "（无回复）"
                        )
                        await agent_conversation.append_message(
                            stream_db, conversation, role="assistant", content=content,
                            tool_calls=[
                                {"tool": step.get("tool"), "status": step.get("status"),
                                 "summary": step.get("summary")}
                                for step in (run_info["steps"] or [])
                            ] or None,
                            token_usage={"total_tokens": (run_info["stats"] or {}).get("total_tokens")},
                            trace_id=trace_id,
                        )
                    await stream_db.commit()
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
                agent_id=run_info["agent_id"],
                task_id=body.task_id,
                conversation_id=run_info["conversation_id"],
                trigger="task_chat" if body.task_id else "chat",
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


@router.post("/confirmations/{confirmation_id}/confirm", response_model=dict)
async def confirm_write(
    confirmation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """确认执行写操作：原子消费确认单 → 派单订单智能体（不重试）→ 只读续跑回查总结"""
    outcome = await orchestrator.resolve_confirmation(
        db, confirmation_id, "confirm", str(_current_user_id(current_user))
    )
    if outcome.get("code") != 0:
        return {"code": outcome["code"], "message": outcome.get("message", "")}
    return {"code": 0, "message": outcome.get("message", ""), "data": outcome.get("data")}


@router.post("/confirmations/{confirmation_id}/cancel", response_model=dict)
async def cancel_write(
    confirmation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """取消写操作确认单：原子消费并丢弃，不产生任何写入"""
    outcome = await orchestrator.resolve_confirmation(
        db, confirmation_id, "cancel", str(_current_user_id(current_user))
    )
    if outcome.get("code") != 0:
        return {"code": outcome["code"], "message": outcome.get("message", "")}
    return {"code": 0, "message": outcome.get("message", ""), "data": outcome.get("data")}


async def _current_agent_context(db: AsyncSession, current_user):
    if not get_settings().AGENT_TASK_ENABLED:
        return None
    user = await db.get(SysUser, int(_current_user_id(current_user)))
    if not user:
        return None
    return await load_agent_context(db, user)


def _visible_tools(ctx) -> list:
    tools = get_all_tools()
    if ctx is None:
        return tools
    return [tool for tool in tools if tool.name in ctx.allowed_tools]


@router.get("/tools", response_model=dict)
async def list_tools(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """返回当前智能体可用工具（按能力过滤）"""
    ctx = await _current_agent_context(db, current_user)
    data = [ToolInfo(name=t.name, description=t.description).model_dump() for t in _visible_tools(ctx)]
    if ctx is not None:
        data.extend(task_tools.task_tool_infos(ctx.allowed_tools))
    return {"code": 0, "data": data}


@router.get("/skills", response_model=dict)
async def list_skills(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("topbar.ai_search", "read")),
):
    """兼容旧接口：返回工具清单（以 skill 格式，按当前智能体能力过滤）"""
    ctx = await _current_agent_context(db, current_user)
    skill_items = [
        {
            "intent": t.name,
            "name": t.display_name or t.name,
            "description": t.description,
            "keywords": t.keywords or [t.name],
            "category": t.category,
        }
        for t in _visible_tools(ctx)
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
