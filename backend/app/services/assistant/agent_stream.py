"""流式 Agent — SSE 流式输出版本：意图识别 → 闲聊直答 / 本地编排器（ReAct）事件透传"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent.context import AgentContext
from app.services.agent.prompt import build_agent_system_prompt
from app.services.ai import ai_service, ChatMessage, ChatOptions
from app.services.assistant import session_store
from app.services.assistant.agent import _load_runtime_config, _recognize_intent
from app.services.assistant.cancellation import CancellationRegistry
from app.services.assistant.hub_reporter import now_iso, report_model_call
from app.services.assistant.orchestrator import (
    LLM_RETRY_CONFIG,
    ThinkTagFilter,
    maybe_summarize,
    resolve_system_prompt,
    run_reaction,
)
from app.services.assistant.retry import RetryExhaustedError, async_retry
from app.services.assistant.run_logger import RunLogger

logger = logging.getLogger(__name__)


def _sse_event(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _client_disconnect_watcher(
    request: Request,
    session_id: str,
) -> None:
    try:
        while True:
            if await request.is_disconnected():
                CancellationRegistry.trigger(session_id, "client_disconnected")
                return
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def run_stream(
    message: str,
    db: AsyncSession,
    session_id: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    trace_id: str = "",
    user_id: str = "",
    request: Optional[Request] = None,
    agent_context: Optional[AgentContext] = None,
    agent_task_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    task_context_text: str = "",
) -> AsyncIterator[str]:
    """流式运行助手：意图识别 → 闲聊直答 / 任务交本地编排器（ReAct 事件透传）"""

    provider_name = ai_service.current_provider()

    rt = await _load_runtime_config(db)
    disabled = set(rt.get("disabled_tools") or [])
    system_prompt = resolve_system_prompt(rt.get("system_prompt"), disabled)
    if agent_context is not None:
        system_prompt = build_agent_system_prompt(system_prompt, agent_context, task_context_text)
    intent_prompt = (rt.get("intent_prompt") or "").strip() or None
    model_override = (rt.get("model_name") or "").strip() or None

    stats: Dict[str, Any] = {"tools_called": [], "tool_rounds": 0, "total_tokens": None}

    run_logger: Optional[RunLogger] = None
    if trace_id:
        try:
            run_logger = RunLogger(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"[stream:{trace_id}] 初始化 RunLogger 失败: {e}")

    if session_id:
        await CancellationRegistry.get_or_create(session_id)

    disconnect_watcher_task: Optional[asyncio.Task] = None
    if request is not None and session_id:
        disconnect_watcher_task = asyncio.create_task(
            _client_disconnect_watcher(request, session_id)
        )

    try:
        if run_logger:
            await run_logger.log("request", {
                "message": message[:500],
                "provider": provider_name,
                "streaming": True,
            })

        if provider_name == "rule_based":
            yield _sse_event("error", {"message": "AI 服务暂不可用，请联系管理员配置 AI 服务。"})
            yield _sse_event("done", {"provider": "rule_based"})
            return

        if CancellationRegistry.is_cancelled(session_id):
            yield _sse_event("cancelled", {"reason": CancellationRegistry.reason(session_id)})
            return

        history = conversation_history or []
        if session_id and not history:
            history = await session_store.get_history(session_id)

        yield _sse_event("thinking", {"stage": "intent", "message": "正在理解您的问题..."})

        intent_started = now_iso()
        intent_start = time.perf_counter()
        intent = await _recognize_intent(message, history, intent_prompt, model_override)
        report_model_call(
            session_id, "意图识别", provider=provider_name,
            started_at=intent_started,
            duration_ms=round((time.perf_counter() - intent_start) * 1000, 2),
        )
        logger.info(f"[stream:{trace_id}] 意图: {intent}")

        if run_logger:
            await run_logger.log("intent_done", {"intent": intent})

        if intent in ("ANALYZE_HISTORY", "GENERAL_CHAT"):
            yield _sse_event("thinking", {"stage": "generating", "message": "正在生成回复..."})

            messages: List[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
            for msg in history[-10:]:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append(ChatMessage(role=role, content=content))
            messages.append(ChatMessage(role="user", content=message))

            messages = await maybe_summarize(messages, run_logger, session_id)

            full_text = ""
            full_thinking = ""
            chat_start = time.perf_counter()
            try:
                @async_retry(LLM_RETRY_CONFIG)
                async def _stream_call():
                    options = ChatOptions(
                        temperature=rt.get("temperature", 0.1),
                        max_tokens=rt.get("max_tokens", 4096),
                        model=model_override,
                        timeout=60,
                    )
                    think_filter = ThinkTagFilter()

                    def _on_thinking(text: str):
                        nonlocal full_thinking
                        full_thinking += text + "\n"
                        yield _sse_event("thinking", {"stage": "reasoning", "text": text})

                    think_filter.set_thinking_callback(_on_thinking)
                    chunks: List[str] = []
                    async for chunk in ai_service.chat_stream(messages, options):
                        cleaned = think_filter.feed(chunk)
                        if cleaned:
                            chunks.append(cleaned)
                    remaining = think_filter.flush()
                    if remaining:
                        chunks.append(remaining)
                    return "".join(chunks)

                result_text = await _stream_call()
                full_text = result_text
                report_model_call(
                    session_id, "生成回复", provider=provider_name,
                    model_override=model_override,
                    duration_ms=round((time.perf_counter() - chat_start) * 1000, 2),
                )
                if full_text:
                    yield _sse_event("delta", {"text": full_text})
            except RetryExhaustedError as e:
                logger.error(f"[stream:{trace_id}] LLM 流式调用重试耗尽: {e}")
                if run_logger:
                    await run_logger.log("error", {"stage": "llm_retry_exhausted", "message": str(e)})
                yield _sse_event("error", {"message": "AI 服务调用失败，请稍后重试。"})
                yield _sse_event("done", {"provider": provider_name, "stats": stats})
                return
            except asyncio.CancelledError:
                yield _sse_event("cancelled", {"reason": "client_disconnected"})
                return
            except Exception as e:
                logger.error(f"[stream:{trace_id}] LLM 流式调用失败: {e}")
                if run_logger:
                    await run_logger.log("error", {"stage": "llm", "message": str(e)})
                yield _sse_event("error", {"message": "AI 服务调用失败，请稍后重试。"})
                yield _sse_event("done", {"provider": provider_name, "stats": stats})
                return

            if CancellationRegistry.is_cancelled(session_id):
                yield _sse_event("cancelled", {"reason": CancellationRegistry.reason(session_id)})
                return

            await _save_conversation(session_id, message, full_text)
            if run_logger:
                await run_logger.log("done", {
                    "intent": intent,
                    "text_length": len(full_text),
                    "thinking_length": len(full_thinking),
                })
            yield _sse_event("done", {
                "provider": provider_name, "intent": intent.lower(), "stats": stats,
                "conversation_id": conversation_id,
            })
            return

        # 任务 → 本地编排器（AI 自主 ReAct，最终总结流式输出）
        stream_text = ""
        stream_done = False
        async for event, data in run_reaction(
            message, history,
            system_prompt=system_prompt, model_override=model_override,
            temperature=rt.get("temperature", 0.1), max_tokens=rt.get("max_tokens", 4096),
            max_tool_rounds=rt.get("max_tool_rounds", 6), max_agent_calls=rt.get("max_agent_calls", 8),
            disabled_tools=disabled, session_id=session_id, trace_id=trace_id, user_id=user_id,
            run_logger=run_logger, provider_name=provider_name,
            stream_final=True,
            db=db, agent_context=agent_context, agent_task_id=agent_task_id,
            task_context_text=task_context_text,
        ):
            if event == "delta":
                stream_text += data.get("text") or ""
            elif event == "done":
                stream_done = True
                if not stream_text and data.get("text"):
                    stream_text = data["text"]
            yield _sse_event(event, data)

        if stream_done and stream_text:
            await _save_conversation(session_id, message, stream_text)
            if run_logger:
                await run_logger.log("done", {
                    "intent": "agent",
                    "text_length": len(stream_text),
                })

    except asyncio.CancelledError:
        yield _sse_event("cancelled", {"reason": "client_disconnected"})
        return
    finally:
        if disconnect_watcher_task is not None:
            disconnect_watcher_task.cancel()
        if run_logger:
            try:
                await run_logger.close()
            except Exception as e:
                logger.warning(f"[stream:{trace_id}] 关闭 RunLogger 失败: {e}")
        if session_id:
            CancellationRegistry.cleanup(session_id)


async def _save_conversation(session_id: str, user_msg: str, assistant_msg: str) -> None:
    if not session_id:
        return
    try:
        await session_store.append_messages(session_id, [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ])
    except Exception as e:
        logger.warning(f"保存会话失败: {e}")
