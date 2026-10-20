"""流式 Agent — SSE 流式输出版本，支持实时推送思考过程、取消、日志"""

import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ai import ai_service, ChatMessage, ChatOptions
from app.services.ai_config import render_system_prompt
from app.services.assistant.tool_registry import get_openai_tools_schema
from app.services.assistant.card_builder import build_cards_from_tool_results
from app.services.assistant import session_store
from app.services.assistant.retry import (
    RetryConfig,
    RetryExhaustedError,
    async_retry,
)
from app.services.assistant.run_logger import RunLogger
from app.services.assistant.cancellation import CancellationRegistry
from app.services.assistant.hub_reporter import now_iso, report_model_call
from app.services.assistant.context_manager import (
    estimate_tokens,
    render_messages_for_summary,
    fallback_sliding_window,
    build_compressed_messages,
    summarize_round,
)
from app.services.assistant.agent import (
    SYSTEM_PROMPT,
    _recognize_intent,
    _execute_tool_with_retry,
    _strip_think_tags,
    _extract_thinking,
    _load_runtime_config,
    _run_routing,
)
from app.services.assistant.task_router import render_route_result

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
TOOL_EXECUTE_TIMEOUT = 30

LLM_RETRY_CONFIG = RetryConfig(
    enabled=True,
    max_retries=3,
    initial_delay=1.0,
    exponential_base=2.0,
    max_delay=15.0,
    retryable_exceptions=(asyncio.TimeoutError, ConnectionError, RuntimeError),
)

_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>", re.DOTALL)


class ThinkTagFilter:
    def __init__(self):
        self._inside_think = False
        self._buffer = ""
        self._thinking_buffer = ""
        self._thinking_callback = None

    def set_thinking_callback(self, callback):
        self._thinking_callback = callback

    def feed(self, chunk: str) -> str:
        output = ""
        self._buffer += chunk

        while self._buffer:
            if self._inside_think:
                end_idx = self._buffer.find("</think>")
                if end_idx != -1:
                    inside = self._buffer[:end_idx]
                    self._thinking_buffer += inside
                    if self._thinking_callback and self._thinking_buffer.strip():
                        try:
                            self._thinking_callback(self._thinking_buffer.strip())
                        except Exception:
                            pass
                    self._thinking_buffer = ""
                    self._buffer = self._buffer[end_idx + 8:]
                    self._inside_think = False
                else:
                    if len(self._buffer) > 100:
                        self._buffer = ""
                    break
            else:
                start_idx = self._buffer.find("<think>")
                if start_idx != -1:
                    output += self._buffer[:start_idx]
                    self._buffer = self._buffer[start_idx + 7:]
                    self._inside_think = True
                elif "<" in self._buffer:
                    lt_idx = self._buffer.rfind("<")
                    potential_tag = self._buffer[lt_idx:]
                    if len(potential_tag) < 7 and "<think>".startswith(potential_tag):
                        output += self._buffer[:lt_idx]
                        self._buffer = potential_tag
                        break
                    else:
                        output += self._buffer
                        self._buffer = ""
                else:
                    output += self._buffer
                    self._buffer = ""

        return output

    def flush(self) -> str:
        if self._inside_think:
            self._buffer = ""
            self._thinking_buffer = ""
            return ""
        result = self._buffer
        self._buffer = ""
        return result


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


async def _maybe_summarize_stream(
    messages: List[Any],
    run_logger: Optional[RunLogger],
) -> List[Any]:
    settings = get_settings()
    if not settings.AI_SUMMARY_ENABLED:
        return messages

    local_tokens = estimate_tokens(messages)
    if local_tokens <= settings.AI_SUMMARY_TOKEN_LIMIT:
        return messages

    if run_logger:
        await run_logger.log("summary_trigger", {
            "local_tokens": local_tokens,
            "threshold": settings.AI_SUMMARY_TOKEN_LIMIT,
        })

    rendered = render_messages_for_summary(messages)
    user_indices = [i for i, m in enumerate(rendered) if m.get("role") == "user" and i > 0]
    if len(user_indices) < 2:
        return messages

    system_msg = next((m for m in rendered if m.get("role") == "system"), None)
    summaries: Dict[int, str] = {}

    async def _summary_chat(msgs, opts):
        return await ai_service.chat(msgs, opts)

    for i, user_idx in enumerate(user_indices[:-1]):
        next_user_idx = user_indices[i + 1]
        exec_msgs = rendered[user_idx + 1: next_user_idx]
        if not exec_msgs:
            continue
        try:
            summary = await summarize_round(exec_msgs, i + 1, _summary_chat)
            if summary:
                summaries[i] = summary
        except Exception as e:
            logger.warning(f"[stream] 摘要轮次 {i + 1} 失败: {e}")

    if summaries:
        new_messages_dict = build_compressed_messages(rendered, system_msg, summaries)
        new_messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in new_messages_dict]
        if run_logger:
            await run_logger.log("summary_done", {
                "rounds_summarized": len(summaries),
                "before_count": len(messages),
                "after_count": len(new_messages),
            })
        return new_messages

    fallback = fallback_sliding_window(rendered, keep_last=6)
    new_messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in fallback]
    if run_logger:
        await run_logger.log("summary_fallback", {
            "before_count": len(messages),
            "after_count": len(new_messages),
        })
    return new_messages


async def _llm_chat_with_retry_stream(messages: List[ChatMessage], options: ChatOptions) -> str:
    return await ai_service.chat(messages, options)


async def _llm_tools_with_retry_stream(messages: List[ChatMessage], tools: List[dict], options: ChatOptions):
    return await ai_service.chat_with_tools(messages, tools, options)


async def run_stream(
    message: str,
    db: AsyncSession,
    session_id: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    trace_id: str = "",
    user_id: str = "",
    request: Optional[Request] = None,
) -> AsyncIterator[str]:
    """流式运行 Agent，通过 SSE 事件逐步推送结果"""

    settings = get_settings()
    provider_name = ai_service.current_provider()

    rt = await _load_runtime_config(db)
    disabled = set(rt.get("disabled_tools") or [])
    system_prompt = render_system_prompt(rt.get("system_prompt") or SYSTEM_PROMPT, disabled)
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
        intent = await _recognize_intent(message, history, intent_prompt)
        report_model_call(
            session_id, "意图识别", provider=provider_name,
            started_at=intent_started,
            duration_ms=round((time.perf_counter() - intent_start) * 1000, 2),
        )
        logger.info(f"[stream:{trace_id}] 意图: {intent}")

        if run_logger:
            await run_logger.log("intent_done", {"intent": intent})

        routing_info = None
        local_result = None
        if intent != "ANALYZE_HISTORY":
            yield _sse_event("thinking", {"stage": "routing", "message": "正在判断任务路由..."})
            routing_info, local_result = await _run_routing(
                message, history,
                enabled=bool(rt.get("routing_enabled", True)),
                model_override=model_override,
                session_id=session_id, trace_id=trace_id, user_id=user_id,
                run_logger=run_logger, diagnostics=stats,
            )
            if routing_info:
                yield _sse_event("routing", routing_info.model_dump())
            if local_result is not None and routing_info is not None:
                if CancellationRegistry.is_cancelled(session_id):
                    yield _sse_event("cancelled", {"reason": CancellationRegistry.reason(session_id)})
                    return
                yield _sse_event("thinking", {"stage": "generating", "message": "正在整理执行结果..."})
                text = await render_route_result(
                    message, routing_info.agent_label or routing_info.agent_key or "执行面智能体",
                    local_result, model_override=model_override,
                )
                if text:
                    yield _sse_event("delta", {"text": text})
                await _save_conversation(session_id, message, text)
                if run_logger:
                    await run_logger.log("done", {
                        "intent": "agent", "route": "local_execution", "text_length": len(text),
                    })
                yield _sse_event("done", {
                    "provider": provider_name, "intent": "agent", "stats": stats,
                    "routing": routing_info.model_dump(),
                })
                return

        if intent in ("ANALYZE_HISTORY", "GENERAL_CHAT"):
            yield _sse_event("thinking", {"stage": "generating", "message": "正在生成回复..."})

            messages: List[Any] = [ChatMessage(role="system", content=system_prompt)]
            for msg in history[-10:]:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append(ChatMessage(role=role, content=content))
            messages.append(ChatMessage(role="user", content=message))

            messages = await _maybe_summarize_stream(messages, run_logger)

            full_text = ""
            full_thinking = ""
            chat_start = time.perf_counter()
            try:
                @async_retry(LLM_RETRY_CONFIG)
                async def _stream_call():
                    options = ChatOptions(temperature=rt.get("temperature", 0.1), max_tokens=rt.get("max_tokens", 4096), model=(rt.get("model_name") or "").strip() or None, timeout=60)
                    think_filter = ThinkTagFilter()

                    def _on_thinking(text: str):
                        nonlocal full_thinking
                        full_thinking += text + "\n"
                        yield _sse_event("thinking", {"stage": "reasoning", "text": text})

                    think_filter.set_thinking_callback(_on_thinking)
                    chunks: list[str] = []
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
            yield _sse_event("done", {"provider": provider_name, "intent": intent.lower(), "stats": stats, "routing": routing_info.model_dump() if routing_info else None})
            return

        tools_schema = get_openai_tools_schema(exclude=disabled)
        if not tools_schema:
            yield _sse_event("error", {"message": "系统未注册任何工具，请联系管理员。"})
            yield _sse_event("done", {"provider": provider_name})
            return

        messages = [ChatMessage(role="system", content=system_prompt)]
        for msg in history[-10:]:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
        messages.append(ChatMessage(role="user", content=message))

        messages = await _maybe_summarize_stream(messages, run_logger)

        all_tool_results: List[Dict[str, Any]] = []
        options = ChatOptions(temperature=rt.get("temperature", 0.1), max_tokens=rt.get("max_tokens", 4096), model=(rt.get("model_name") or "").strip() or None, timeout=120)

        for round_idx in range(rt.get("max_tool_rounds", MAX_TOOL_ROUNDS)):
            if CancellationRegistry.is_cancelled(session_id):
                yield _sse_event("cancelled", {"reason": CancellationRegistry.reason(session_id)})
                return

            yield _sse_event("thinking", {
                "stage": "llm_call",
                "round": round_idx + 1,
                "message": f"正在分析（第{round_idx + 1}轮）...",
            })

            round_start = time.perf_counter()
            try:
                @async_retry(LLM_RETRY_CONFIG)
                async def _tools_call():
                    return await ai_service.chat_with_tools(messages, tools_schema, options)

                result = await _tools_call()
            except RetryExhaustedError as e:
                logger.error(f"[stream:{trace_id}] LLM 调用重试耗尽 (round {round_idx + 1}): {e}")
                if run_logger:
                    await run_logger.log("error", {"stage": "llm_retry_exhausted", "round": round_idx + 1})
                yield _sse_event("error", {"message": "AI 服务调用失败，请稍后重试。"})
                yield _sse_event("done", {"provider": provider_name, "stats": stats})
                return
            except Exception as e:
                logger.error(f"[stream:{trace_id}] LLM 调用失败 (round {round_idx + 1}): {e}")
                if run_logger:
                    await run_logger.log("error", {"stage": "llm", "round": round_idx + 1, "message": str(e)})
                yield _sse_event("error", {"message": "AI 服务调用失败，请稍后重试。"})
                yield _sse_event("done", {"provider": provider_name, "stats": stats})
                return

            if result.usage and result.usage.total_tokens:
                stats["total_tokens"] = result.usage.total_tokens

            report_model_call(
                session_id, f"大模型分析（第{round_idx + 1}轮）", provider=provider_name,
                model_override=model_override, token_usage=result.usage,
                duration_ms=round((time.perf_counter() - round_start) * 1000, 2),
            )

            if run_logger:
                await run_logger.log("llm_response", {
                    "round": round_idx + 1,
                    "has_tool_calls": bool(result.tool_calls),
                    "tool_call_count": len(result.tool_calls),
                    "usage": {
                        "prompt_tokens": result.usage.prompt_tokens if result.usage else 0,
                        "completion_tokens": result.usage.completion_tokens if result.usage else 0,
                        "total_tokens": result.usage.total_tokens if result.usage else 0,
                    } if result.usage else None,
                })

            if CancellationRegistry.is_cancelled(session_id):
                yield _sse_event("cancelled", {"reason": CancellationRegistry.reason(session_id)})
                return

            if not result.tool_calls:
                raw_text = result.text or ""
                text = _strip_think_tags(raw_text)
                thinking = _extract_thinking(raw_text)
                if thinking:
                    yield _sse_event("thinking", {"stage": "reasoning", "text": thinking})
                if text:
                    yield _sse_event("delta", {"text": text})

                if all_tool_results:
                    cards = build_cards_from_tool_results(all_tool_results)
                    if cards:
                        yield _sse_event("cards", {
                            "cards": [c.model_dump() for c in cards],
                        })

                await _save_conversation(session_id, message, text)
                if run_logger:
                    await run_logger.log("done", {
                        "intent": "agent",
                        "text_length": len(text),
                        "tool_count": len(all_tool_results),
                    })
                yield _sse_event("done", {"provider": provider_name, "intent": "agent", "stats": stats, "routing": routing_info.model_dump() if routing_info else None})
                return

            tool_messages = []
            for tc in result.tool_calls:
                if tc.name not in stats["tools_called"]:
                    stats["tools_called"].append(tc.name)
                stats["tool_rounds"] = round_idx + 1
                yield _sse_event("tool_start", {
                    "name": tc.name,
                    "arguments": tc.arguments,
                })

                data = await _execute_tool_with_retry(db, tc.name, tc.arguments, timeout=rt.get("tool_execute_timeout", TOOL_EXECUTE_TIMEOUT), disabled_tools=disabled, trace_id=session_id)
                has_error = "error" in data

                yield _sse_event("tool_done", {
                    "name": tc.name,
                    "success": not has_error,
                    "item_count": data.get("total", 0) if not has_error else 0,
                })

                if run_logger:
                    await run_logger.log("tool_call", {
                        "round": round_idx + 1,
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "success": not has_error,
                        "item_count": data.get("total", 0) if not has_error else 0,
                    })

                if not has_error:
                    all_tool_results.append({"tool": tc.name, "data": data})

                tool_output = json.dumps(data, ensure_ascii=False, default=str)
                tool_msg = ChatMessage(role="tool", content=tool_output)
                tool_msg.tool_call_id = tc.id  # type: ignore
                tool_messages.append(tool_msg)

            assistant_msg = ChatMessage(role="assistant", content=result.text or "")
            assistant_msg.tool_calls = [  # type: ignore
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                }
                for tc in result.tool_calls
            ]
            messages.append(assistant_msg)
            messages.extend(tool_messages)

        yield _sse_event("thinking", {"stage": "summarizing", "message": "正在生成总结..."})

        full_text = ""
        full_thinking = ""
        summary_start = time.perf_counter()
        try:
            options_summary = ChatOptions(temperature=0.1, max_tokens=4096, timeout=120)
            think_filter = ThinkTagFilter()
            chunks_buffer: list[str] = []

            def _on_thinking(text: str):
                nonlocal full_thinking
                full_thinking += text + "\n"
                yield _sse_event("thinking", {"stage": "reasoning", "text": text})

            think_filter.set_thinking_callback(_on_thinking)
            async for chunk in ai_service.chat_stream(messages, options_summary):
                cleaned = think_filter.feed(chunk)
                if cleaned:
                    chunks_buffer.append(cleaned)
            remaining = think_filter.flush()
            if remaining:
                chunks_buffer.append(remaining)
            full_text = "".join(chunks_buffer)
            report_model_call(
                session_id, "生成总结", provider=provider_name,
                model_override=model_override,
                duration_ms=round((time.perf_counter() - summary_start) * 1000, 2),
            )
            if full_text:
                yield _sse_event("delta", {"text": full_text})
        except Exception as e:
            logger.error(f"[stream:{trace_id}] 最终总结流式输出失败: {e}")
            full_text = "查询完成，但生成总结时出现问题。"
            yield _sse_event("delta", {"text": full_text})

        if all_tool_results:
            cards = build_cards_from_tool_results(all_tool_results)
            if cards:
                yield _sse_event("cards", {"cards": [c.model_dump() for c in cards]})

        await _save_conversation(session_id, message, full_text)
        if run_logger:
            await run_logger.log("done", {
                "intent": "agent",
                "text_length": len(full_text),
                "tool_count": len(all_tool_results),
                "max_rounds_reached": True,
            })
        yield _sse_event("done", {"provider": provider_name, "intent": "agent", "stats": stats, "routing": routing_info.model_dump() if routing_info else None})

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
