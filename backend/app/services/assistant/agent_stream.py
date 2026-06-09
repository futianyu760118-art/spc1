"""流式 Agent — SSE 流式输出版本，支持实时推送思考过程和结果"""

import json
import logging
import re
import asyncio
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import ai_service, ChatMessage, ChatOptions, NotSupportedError
from app.services.assistant.tool_registry import get_tool, get_openai_tools_schema
from app.services.assistant.card_builder import build_cards_from_tool_results
from app.services.assistant import session_store

logger = logging.getLogger(__name__)

# ─── 配置 ───────────────────────────────────────────────────
MAX_TOOL_ROUNDS = 5
TOOL_EXECUTE_TIMEOUT = 30
MAX_RETRIES = 1

# Qwen3 系列模型会输出 <think>...</think> 标签
_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>", re.DOTALL)


def _strip_think_tags(text: str) -> str:
    if not text:
        return text
    cleaned = _THINK_TAG_RE.sub("", text).strip()
    return cleaned or text


class ThinkTagFilter:
    """流式输出时过滤 <think>...</think> 标签的状态机。
    
    因为流式 chunk 可能在标签中间断开，需要缓冲处理。
    """

    def __init__(self):
        self._inside_think = False
        self._buffer = ""

    def feed(self, chunk: str) -> str:
        """输入一个 chunk，返回应该输出的文本（可能为空）"""
        output = ""
        self._buffer += chunk

        while self._buffer:
            if self._inside_think:
                # 在 <think> 内部，寻找 </think>
                end_idx = self._buffer.find("</think>")
                if end_idx != -1:
                    # 找到结束标签，跳过整个 think 块
                    self._buffer = self._buffer[end_idx + 8:]
                    self._inside_think = False
                else:
                    # 还没找到结束标签，可能还没收完，清空 buffer 等待更多数据
                    # 但保留可能是 </think> 前缀的部分
                    if len(self._buffer) > 100:
                        # 如果 buffer 太长还没结束，可能是异常情况，丢弃
                        self._buffer = ""
                    break
            else:
                # 不在 <think> 内部，寻找 <think>
                start_idx = self._buffer.find("<think>")
                if start_idx != -1:
                    # 输出 <think> 之前的内容
                    output += self._buffer[:start_idx]
                    self._buffer = self._buffer[start_idx + 7:]
                    self._inside_think = True
                elif "<" in self._buffer:
                    # 可能是 <think> 的前缀（如 "<thi"），保守处理
                    lt_idx = self._buffer.rfind("<")
                    potential_tag = self._buffer[lt_idx:]
                    if len(potential_tag) < 7 and "<think>".startswith(potential_tag):
                        # 可能是不完整的 <think> 标签，保留在 buffer
                        output += self._buffer[:lt_idx]
                        self._buffer = potential_tag
                        break
                    else:
                        # 不是 <think> 前缀，全部输出
                        output += self._buffer
                        self._buffer = ""
                else:
                    # 没有 < 字符，全部输出
                    output += self._buffer
                    self._buffer = ""

        return output

    def flush(self) -> str:
        """结束时刷出剩余 buffer"""
        if self._inside_think:
            # think 标签没闭合，丢弃
            self._buffer = ""
            return ""
        result = self._buffer
        self._buffer = ""
        return result


# ─── SSE 事件类型 ─────────────────────────────────────────────
# event: thinking   — 正在思考/处理中的状态
# event: tool_start — 开始调用工具
# event: tool_done  — 工具调用完成
# event: delta      — 流式文本增量
# event: cards      — 卡片数据
# event: suggestions— 建议操作
# event: done       — 完成
# event: error      — 错误


def _sse_event(event: str, data: Any) -> str:
    """格式化 SSE 事件"""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _execute_tool(
    db: AsyncSession,
    tool_name: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """执行单个工具，带超时和重试"""
    tool_def = get_tool(tool_name)
    if not tool_def:
        return {"error": f"工具 {tool_name} 不存在"}

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            data = await asyncio.wait_for(
                tool_def.execute(db, params),
                timeout=TOOL_EXECUTE_TIMEOUT,
            )
            return data
        except asyncio.TimeoutError:
            last_error = f"工具 {tool_name} 执行超时"
            logger.warning(f"{last_error} (attempt {attempt + 1})")
        except Exception as e:
            last_error = f"工具 {tool_name} 执行失败: {str(e)}"
            logger.error(f"{last_error} (attempt {attempt + 1})")

        if attempt < MAX_RETRIES:
            await asyncio.sleep(0.5)

    return {"error": last_error}


# 导入 agent 模块中的 SYSTEM_PROMPT 和意图识别
from app.services.assistant.agent import SYSTEM_PROMPT, _recognize_intent


async def run_stream(
    message: str,
    db: AsyncSession,
    session_id: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    trace_id: str = "",
) -> AsyncIterator[str]:
    """流式运行 Agent，通过 SSE 事件逐步推送结果"""

    provider_name = ai_service.current_provider()

    # LLM 不可用
    if provider_name == "rule_based":
        yield _sse_event("error", {"message": "AI 服务暂不可用，请联系管理员配置 AI 服务。"})
        yield _sse_event("done", {"provider": "rule_based"})
        return

    # 加载会话历史
    history = conversation_history or []
    if session_id and not history:
        history = await session_store.get_history(session_id)

    # 意图识别
    yield _sse_event("thinking", {"stage": "intent", "message": "正在理解您的问题..."})
    intent = await _recognize_intent(message, history)
    logger.info(f"[stream:{trace_id}] 意图: {intent}")

    # ─── 非查询意图：直接流式回复 ─────────────────────────────
    if intent in ("ANALYZE_HISTORY", "GENERAL_CHAT"):
        yield _sse_event("thinking", {"stage": "generating", "message": "正在生成回复..."})

        messages: List[Any] = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
        for msg in history[-10:]:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
        messages.append(ChatMessage(role="user", content=message))

        full_text = ""
        try:
            options = ChatOptions(temperature=0.3, max_tokens=4096, timeout=60)
            think_filter = ThinkTagFilter()
            async for chunk in ai_service.chat_stream(messages, options):
                cleaned = think_filter.feed(chunk)
                if cleaned:
                    full_text += cleaned
                    yield _sse_event("delta", {"text": cleaned})
            # 刷出剩余内容
            remaining = think_filter.flush()
            if remaining:
                full_text += remaining
                yield _sse_event("delta", {"text": remaining})
        except Exception as e:
            logger.error(f"[stream:{trace_id}] LLM 流式调用失败: {e}")
            yield _sse_event("error", {"message": "AI 服务调用失败，请稍后重试。"})
            yield _sse_event("done", {"provider": provider_name})
            return

        # 保存会话
        await _save_conversation(session_id, message, full_text)
        yield _sse_event("done", {"provider": provider_name, "intent": intent.lower()})
        return

    # ─── QUERY_DATA 意图：工具调用 + 流式总结 ─────────────────
    tools_schema = get_openai_tools_schema()
    if not tools_schema:
        yield _sse_event("error", {"message": "系统未注册任何工具，请联系管理员。"})
        yield _sse_event("done", {"provider": provider_name})
        return

    # 构建消息列表
    messages: List[Any] = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
    for msg in history[-10:]:
        role = msg.get("role")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append(ChatMessage(role=role, content=content))
    messages.append(ChatMessage(role="user", content=message))

    # Tool Calling 循环
    all_tool_results: List[Dict[str, Any]] = []
    options = ChatOptions(temperature=0.1, max_tokens=4096, timeout=120)

    for round_idx in range(MAX_TOOL_ROUNDS):
        yield _sse_event("thinking", {
            "stage": "llm_call",
            "round": round_idx + 1,
            "message": f"正在分析（第{round_idx + 1}轮）...",
        })

        try:
            result = await ai_service.chat_with_tools(messages, tools_schema, options)
        except Exception as e:
            logger.error(f"[stream:{trace_id}] LLM 调用失败 (round {round_idx + 1}): {e}")
            yield _sse_event("error", {"message": "AI 服务调用失败，请稍后重试。"})
            yield _sse_event("done", {"provider": provider_name})
            return

        # LLM 直接回复（无 tool call）— 流式输出最终文本
        if not result.tool_calls:
            text = _strip_think_tags(result.text or "")
            if text:
                yield _sse_event("delta", {"text": text})

            # 构建卡片
            if all_tool_results:
                cards = build_cards_from_tool_results(all_tool_results)
                if cards:
                    yield _sse_event("cards", {
                        "cards": [c.model_dump() for c in cards],
                    })

            # 保存会话
            await _save_conversation(session_id, message, text)
            yield _sse_event("done", {"provider": provider_name, "intent": "agent"})
            return

        # 执行 Tool 调用
        tool_messages = []
        for tc in result.tool_calls:
            yield _sse_event("tool_start", {
                "name": tc.name,
                "arguments": tc.arguments,
            })

            data = await _execute_tool(db, tc.name, tc.arguments)
            has_error = "error" in data

            yield _sse_event("tool_done", {
                "name": tc.name,
                "success": not has_error,
                "item_count": data.get("total", 0) if not has_error else 0,
            })

            if not has_error:
                all_tool_results.append({"tool": tc.name, "data": data})

            tool_output = json.dumps(data, ensure_ascii=False, default=str)
            tool_msg = ChatMessage(role="tool", content=tool_output)
            tool_msg.tool_call_id = tc.id  # type: ignore
            tool_messages.append(tool_msg)

        # 构造 assistant 消息（含 tool_calls）
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

    # 超过最大轮次 — 流式生成最终总结
    yield _sse_event("thinking", {"stage": "summarizing", "message": "正在生成总结..."})

    full_text = ""
    try:
        think_filter = ThinkTagFilter()
        async for chunk in ai_service.chat_stream(messages, options):
            cleaned = think_filter.feed(chunk)
            if cleaned:
                full_text += cleaned
                yield _sse_event("delta", {"text": cleaned})
        remaining = think_filter.flush()
        if remaining:
            full_text += remaining
            yield _sse_event("delta", {"text": remaining})
    except Exception as e:
        logger.error(f"[stream:{trace_id}] 最终总结流式输出失败: {e}")
        full_text = "查询完成，但生成总结时出现问题。"
        yield _sse_event("delta", {"text": full_text})

    # 卡片
    if all_tool_results:
        cards = build_cards_from_tool_results(all_tool_results)
        if cards:
            yield _sse_event("cards", {"cards": [c.model_dump() for c in cards]})

    await _save_conversation(session_id, message, full_text)
    yield _sse_event("done", {"provider": provider_name, "intent": "agent"})


async def _save_conversation(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """保存对话到会话存储"""
    if not session_id:
        return
    try:
        await session_store.append_messages(session_id, [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ])
    except Exception as e:
        logger.warning(f"保存会话失败: {e}")
