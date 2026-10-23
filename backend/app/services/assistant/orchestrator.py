"""本地编排器 — AI 自主 ReAct 循环 + 三道硬闸门（修订版方案）。

- 闸门 1 能力边界：只暴露 3 个执行面智能体工具，入参白名单逐步校验；能力缺口与跨系统不支持在系统提示词显式声明；
- 闸门 2 步数与循环：LLM 轮数 / 智能体调用次数 / 重复调用拦截 / 连续同智能体提示换策略 / 单轮总预算 / 结果裁剪；
- 闸门 3 写操作确认：call_order_agent 一律拦截，先经查询智能体读旧值生成「旧值 → 新值」确认单
  （Redis 10 分钟过期，原子消费），用户确认后才派单订单智能体；取消不产生任何写入。

run_reaction 为共享事件流（async generator，产出 (event, data) 元组），供流式 / 非流式复用；
resolve_confirmation 供确认 / 取消端点调用，执行写入并只读续跑生成回查总结。
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from uuid import uuid4

from app.core.config import get_settings
from app.services.ai import ai_service, ChatMessage, ChatOptions
from app.services.ai_config import ASSISTANT_SCOPE, get_scope_config, render_system_prompt
from app.services.assistant import session_store, write_confirmation
from app.services.assistant.agent_tools import (
    AGENT_TOOL_LABELS,
    CAPABILITY_BY_TOOL,
    TOOL_TIMEOUT_S,
    build_agent_tools_schema,
    execute_agent_tool,
    query_order_current_fields,
    validate_tool_input,
)
from app.services.assistant.card_builder import build_cards_from_query_results
from app.services.assistant.cancellation import CancellationRegistry
from app.services.assistant.completeness_rules import check_completeness, refresh_rules
from app.services.assistant.context_manager import (
    build_compressed_messages,
    estimate_tokens,
    fallback_sliding_window,
    render_messages_for_summary,
    should_summarize,
    summarize_round,
)
from app.services.assistant.hub_reporter import now_iso, report_assistant_event, report_model_call
from app.services.assistant.retry import RetryConfig, RetryExhaustedError, async_retry
from app.services.assistant.run_logger import RunLogger
from app.services.assistant.task_router import (
    ORDER_FIELDS_DOC,
    QUERY_CATALOG,
    REASONING_TASK_TYPES,
    trim_result,
)
from app.services.execution_agents import AGENT_SPECS, call_agent_run
from app.services.notification.assistant_notify import (
    BIZ_NOTIFY_CONFIG,
    notify_agent_change,
    notify_agent_gap,
)

logger = logging.getLogger(__name__)

# 首期硬闸门参数（可经运行时配置覆盖轮数与调用次数）
DEFAULT_LIMITS = {
    "max_llm_rounds": 6,
    "max_agent_calls": 8,
    "max_consecutive_same_agent": 3,
    "total_budget_s": 300.0,
    "trim_max_items": 20,
    "trim_max_chars": 8000,
}

# 写确认后的续跑（只读回查 + 总结）：更小的步数与预算
CONTINUATION_LIMITS = {
    "max_llm_rounds": 3,
    "max_agent_calls": 3,
    "max_consecutive_same_agent": 3,
    "total_budget_s": 150.0,
    "trim_max_items": 20,
    "trim_max_chars": 8000,
}

LLM_RETRY_CONFIG = RetryConfig(
    enabled=True,
    max_retries=3,
    initial_delay=1.0,
    exponential_base=2.0,
    max_delay=15.0,
    retryable_exceptions=(asyncio.TimeoutError, ConnectionError, RuntimeError),
)

_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>", re.DOTALL)


def _strip_think_tags(text: str) -> str:
    if not text:
        return text
    cleaned = _THINK_TAG_RE.sub("", text).strip()
    return cleaned or text


def _extract_thinking(text: str) -> str:
    if not text:
        return ""
    matches = _THINK_TAG_RE.findall(text)
    return "\n".join(m.replace("<think>", "").replace("</think>", "").strip() for m in matches).strip()


class ThinkTagFilter:
    """流式输出中拆分 <think>...</think> 标签，思考内容经回调透出，正文原样返回。"""

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


def build_default_system_prompt() -> str:
    """内置系统提示词：3 个智能体工具 + hub_query 跨系统查询、能力缺口、写操作确认。"""
    query_lines = "\n".join(
        f"- {c['path']}：{c['name']}；可用参数 {c['params']}" for c in QUERY_CATALOG
    )
    reasoning_lines = "\n".join(f"- {c['type']}：{c['desc']}" for c in REASONING_TASK_TYPES)
    return f"""你是供应链与生产协同中台的智能决策助手。你可以调用执行面智能体完成查询、分析与订单修改，或经 hub_query 查询外部系统只读数据（当前 PLM 研发项目），并自主决定调用哪几个工具、调用顺序与次数。

可用智能体工具（每一轮只能调用一个）：
1) call_query_agent（查询智能体，只读）——path 白名单：
{query_lines}
- params 只放用户消息中可确定的筛选条件，不要编造编号

2) call_reasoning_agent（推理智能体，只读分析，带证据，耗时较长）——task_type 枚举：
{reasoning_lines}

3) call_order_agent（订单智能体，写操作）——字段白名单：
{ORDER_FIELDS_DOC}
- 写操作不可撤销；系统会自动拦截并生成「旧值 → 新值」确认单，用户确认后才执行
- fields 只放用户明确要求修改的字段与日期；日期统一 YYYY-MM-DD；清空用 null

4) hub_query（Hub 统一查询，只读，跨系统）——查询其他系统的数据：
- capability 只能选工具 schema 白名单枚举（当前仅 query_plm：查询 PLM 研发项目）
- params 只放用户消息中可确定的值（query_plm 支持 keyword：项目号或关键字，如 HJ.26033.V1.256JY）

使用规则：
- 自主规划步骤：需要数据时先查询，需要结论时先推理分析，需要改数据时先查旧值再发起写操作
- 不要重复调用完全相同参数的工具；同工具换参数可以继续查
- 查询结果为空时如实告知，不要虚构数据

能力边界（首期暂不支持，遇到时明确告知用户"暂不支持"并建议去对应页面，绝不编造数据）：
- 采购订单查询、跑单管理、采购开票/付款、交期变更历史（ETA）
- 客户查询、系统用户查询、驾驶舱概览、行动建议（简报/跟进/周总结）
- ERP / MES / OA 等未开放系统的数据与操作；跨系统写操作不支持（只读查询仅限 hub_query 能力白名单）

回复格式要求（严格遵守）：
- 使用简洁的 Markdown 格式输出
- 用 **加粗** 标注关键信息（订单号、数量、日期、风险等级）
- 多条数据用表格呈现：| 订单号 | 客户 | 交期 | 状态 |
- 段落之间空一行，控制篇幅在合理范围内
- 不要重复工具返回的原始 JSON 数据
- 不要使用 HTML 标签，不要输出 <think> 标签或思考过程"""


SYSTEM_PROMPT = build_default_system_prompt()

# 已随「助手去工具化」移除的本地工具；数据库里保存的旧提示词仍会引用它们
_REMOVED_TOOL_NAMES = (
    "search_orders",
    "search_purchase_orders",
    "search_materials",
    "search_kit_analysis",
    "search_bom_details",
    "search_production",
    "search_run_orders",
    "search_exceptions",
    "search_invoices",
    "search_eta_updates",
    "search_basicdata",
    "search_users",
    "get_dashboard_summary",
    "suggest_actions",
)


def resolve_system_prompt(stored_prompt: Optional[str], disabled_tools: Optional[List[str]] = None) -> str:
    """数据库提示词若仍引用已移除工具则回退内置提示词，避免 LLM 按旧能力目录编造参数。"""
    prompt = (stored_prompt or "").strip()
    if prompt and any(name in prompt for name in _REMOVED_TOOL_NAMES):
        logger.warning("[orchestrator] 数据库系统提示词引用已移除的本地工具，回退内置提示词")
        prompt = ""
    return render_system_prompt(prompt or SYSTEM_PROMPT, disabled_tools)


@async_retry(LLM_RETRY_CONFIG)
async def _llm_tools_with_retry(messages: List[ChatMessage], tools: List[dict], options: ChatOptions):
    return await ai_service.chat_with_tools(messages, tools, options)


@async_retry(LLM_RETRY_CONFIG)
async def _llm_chat_with_retry(messages: List[ChatMessage], options: ChatOptions) -> str:
    return await ai_service.chat(messages, options)


async def maybe_summarize(
    messages: List[ChatMessage],
    run_logger: Optional[RunLogger],
    session_id: str = "",
) -> List[ChatMessage]:
    """上下文超限时按轮次摘要压缩；失败回退滑动窗口。"""
    settings = get_settings()
    if not settings.AI_SUMMARY_ENABLED:
        return messages

    local_tokens = estimate_tokens(messages)
    if not should_summarize(local_tokens, None, settings.AI_SUMMARY_TOKEN_LIMIT, True):
        return messages

    if run_logger:
        await run_logger.log("summary_trigger", {
            "local_tokens": local_tokens,
            "threshold": settings.AI_SUMMARY_TOKEN_LIMIT,
            "message_count": len(messages),
        })

    rendered = render_messages_for_summary(messages)
    user_indices = [i for i, m in enumerate(rendered) if m.get("role") == "user" and i > 0]
    if len(user_indices) < 2:
        return messages

    system_msg = next((m for m in rendered if m.get("role") == "system"), None)

    async def _summary_chat(msgs, opts):
        return await ai_service.chat(msgs, opts)

    summaries: Dict[int, str] = {}
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
            logger.warning(f"[orchestrator] 摘要轮次 {i + 1} 失败: {e}")

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
            "after_count": len(fallback),
        })
    return new_messages


def _new_step(
    step_id: int,
    tool_name: str,
    args: Dict[str, Any],
    *,
    status: str,
    summary: str = "",
    error: Optional[str] = None,
    item_count: Optional[int] = None,
    duration_ms: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "step_id": step_id,
        "tool": tool_name,
        "agent_label": AGENT_TOOL_LABELS.get(tool_name, tool_name),
        "capability": CAPABILITY_BY_TOOL.get(tool_name, ""),
        "path": args.get("path") if tool_name == "call_query_agent" else None,
        "task_type": args.get("task_type") if tool_name == "call_reasoning_agent" else None,
        "order_no": args.get("order_no") if tool_name == "call_order_agent" else None,
        "status": status,
        "summary": summary,
        "error": error,
        "item_count": item_count,
        "duration_ms": duration_ms,
    }


def _step_summary(tool_name: str, args: Dict[str, Any]) -> str:
    if tool_name == "call_query_agent":
        path = args.get("path") or ""
        name = next((c["name"] for c in QUERY_CATALOG if c["path"] == path), path)
        return f"查询 {name}"
    if tool_name == "call_reasoning_agent":
        return f"分析 {args.get('task_type') or ''}"
    if tool_name == "hub_query":
        return f"查询外部系统 {args.get('capability') or ''}"
    return f"修改订单 {args.get('order_no') or ''}"


def _assistant_tool_msg(
    text: str, tool_calls: List[Any], reasoning_content: Optional[str] = None
) -> ChatMessage:
    return ChatMessage(
        role="assistant",
        content=text or "",
        reasoning_content=reasoning_content or None,
        tool_calls=[
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False, default=str)},
            }
            for tc in tool_calls
        ],
    )


def _tool_result_msg(tool_call_id: str, content: Any) -> ChatMessage:
    payload = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
    return ChatMessage(role="tool", content=payload, tool_call_id=tool_call_id)


async def _final_answer_text(
    messages: List[ChatMessage],
    options: ChatOptions,
    *,
    session_id: str,
    provider_name: str,
    model_override: Optional[str],
    stream_final: bool,
    label: str,
) -> Tuple[str, List[str]]:
    """生成最终答复文本，返回 (text, thinking_parts)。"""
    thinking_parts: List[str] = []
    started_at = now_iso()
    start = time.perf_counter()
    if stream_final:
        think_filter = ThinkTagFilter()
        chunks: List[str] = []

        def _on_thinking(text: str):
            thinking_parts.append(text)

        think_filter.set_thinking_callback(_on_thinking)
        async for chunk in ai_service.chat_stream(messages, options):
            cleaned = think_filter.feed(chunk)
            if cleaned:
                chunks.append(cleaned)
        remaining = think_filter.flush()
        if remaining:
            chunks.append(remaining)
        text = "".join(chunks)
    else:
        raw = await _llm_chat_with_retry(messages, options)
        text = raw if isinstance(raw, str) else (raw.text or "")
        thinking = _extract_thinking(text)
        if thinking:
            thinking_parts.append(thinking)
        text = _strip_think_tags(text)
    report_model_call(
        session_id, label, provider=provider_name, model_override=model_override,
        started_at=started_at, duration_ms=round((time.perf_counter() - start) * 1000, 2),
    )
    return text, [t for t in thinking_parts if t]


async def _gap_missing(
    *, biz_type: str, biz_no: str, values: Dict[str, Any]
) -> list:
    await refresh_rules()
    return check_completeness(biz_type=biz_type, biz_no=biz_no, values=values)


def _schedule_gap_notify(
    *, biz_type: str, biz_no: str, missing: list, initiator_user_id: str
) -> None:
    notify_agent_gap(
        biz_type=biz_type, biz_no=biz_no,
        missing_keys=[key for key, _ in missing],
        missing_labels=[label for _, label in missing],
        initiator_user_id=initiator_user_id,
    )


async def _check_query_gaps(
    args: Dict[str, Any], result: Dict[str, Any], user_id: str
) -> Optional[Dict[str, Any]]:
    try:
        path = args.get("path")
        biz_type = next(
            (key for key, cfg in BIZ_NOTIFY_CONFIG.items()
             if path in (cfg.get("query_paths") or [])),
            None,
        )
        if not biz_type:
            return None
        params = args.get("params") or {}
        order_no = params.get("order_no") or params.get("keyword")
        if not order_no:
            return None
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list):
            return None
        row = next(
            (item for item in items
             if isinstance(item, dict) and str(item.get("order_no") or "") == str(order_no)),
            None,
        )
        if row is None:
            logger.info("gap_skip reason=no_match path=%s biz_no=%s", path, order_no)
            return None
        missing = await _gap_missing(
            biz_type=biz_type, biz_no=str(order_no), values=row
        )
        logger.info("gap_check biz_type=%s biz_no=%s missing=%s",
                    biz_type, order_no, len(missing))
        if not missing:
            return {"missing": []}
        _schedule_gap_notify(
            biz_type=biz_type, biz_no=str(order_no), missing=missing,
            initiator_user_id=user_id,
        )
        return {"missing": [label for _, label in missing]}
    except Exception as e:
        logger.warning("gap check failed path=%s: %s", args.get("path"), e)
        return None


async def run_reaction(
    message: str,
    history: List[Dict[str, Any]],
    *,
    system_prompt: str,
    model_override: Optional[str],
    temperature: float,
    max_tokens: int,
    max_tool_rounds: int,
    max_agent_calls: int,
    disabled_tools: Optional[set] = None,
    session_id: str = "",
    trace_id: str = "",
    user_id: str = "",
    run_logger: Optional[RunLogger] = None,
    provider_name: str = "",
    limits: Optional[Dict[str, Any]] = None,
    include_order_tool: bool = True,
    stream_final: bool = False,
    task_id: Optional[str] = None,
    step_id_base: int = 0,
    gap_notify: bool = True,
) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """AI 自主 ReAct 循环：LLM 逐步决定调用哪个智能体，编排器负责校验、执行、拦截与审计。

    task_id 缺省时生成（一次助手请求 = 一个任务，Hub 按 traceId+taskId 归并）；
    step_id_base 用于写确认后的续跑，使同一任务的 stepId 延续不重号。

    事件流：
    - thinking / delta / cards / confirmation_required / cancelled / error
    - step_started / step_completed（步骤时间线）
    - done（终态，携带 steps / stats / diagnostics / partial / failed）
    """
    lim = {**DEFAULT_LIMITS, **(limits or {})}
    lim["max_llm_rounds"] = max(1, min(int(max_tool_rounds), lim["max_llm_rounds"]))
    lim["max_agent_calls"] = max(1, min(int(max_agent_calls), lim["max_agent_calls"]))
    provider = provider_name or ai_service.current_provider()
    task_id = task_id or f"task-{uuid4().hex}"
    logger.info(f"[orchestrator:{trace_id}] session_id={session_id} task_id={task_id}")

    def _next_step_id() -> int:
        return step_id_base + len(steps) + 1

    steps: List[Dict[str, Any]] = []
    query_results: List[Dict[str, Any]] = []
    diagnostics: Dict[str, Any] = {"llm_rounds": [], "tools": [], "errors": [], "total_tokens": None}
    stats: Dict[str, Any] = {"tools_called": [], "tool_rounds": 0, "total_tokens": None}

    tools_schema = build_agent_tools_schema(include_order=include_order_tool, exclude=disabled_tools or set())

    messages: List[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
    for msg in history[-10:]:
        role, content = msg.get("role"), msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append(ChatMessage(role=role, content=content))
    messages.append(ChatMessage(role="user", content=message))
    messages = await maybe_summarize(messages, run_logger, session_id)

    options = ChatOptions(
        temperature=temperature, max_tokens=max_tokens, model=model_override, timeout=120
    )

    def _done_payload(
        text: str,
        *,
        confirmation: Optional[Dict[str, Any]] = None,
        partial: bool = False,
        partial_reason: str = "",
        failed: bool = False,
    ) -> Dict[str, Any]:
        return {
            "provider": provider,
            "intent": "agent",
            "text": text,
            "steps": steps,
            "confirmation": confirmation,
            "partial": partial,
            "partial_reason": partial_reason,
            "failed": failed,
            "stats": stats,
            "diagnostics": diagnostics,
        }

    if not tools_schema:
        text, thinking = await _final_answer_text(
            messages, options, session_id=session_id, provider_name=provider,
            model_override=model_override, stream_final=stream_final, label="生成回复",
        )
        for t in thinking:
            yield ("thinking", {"stage": "reasoning", "text": t})
        if text:
            yield ("delta", {"text": text})
        yield ("done", _done_payload(text))
        return

    total_start = time.perf_counter()
    agent_calls = 0
    last_tool_key: Optional[str] = None
    last_tool_name: Optional[str] = None
    consecutive_same_agent = 0
    last_total_tokens: Optional[int] = None

    for round_idx in range(1, lim["max_llm_rounds"] + 1):
        if session_id and CancellationRegistry.is_cancelled(session_id):
            reason = CancellationRegistry.reason(session_id)
            if run_logger:
                await run_logger.log("cancel", {"reason": reason, "round": round_idx})
            yield ("cancelled", {"reason": reason})
            return

        if time.perf_counter() - total_start > lim["total_budget_s"]:
            partial_reason = "单轮总预算超时，返回已完成步骤"
            if run_logger:
                await run_logger.log("note", {"message": partial_reason})
            break

        yield ("thinking", {
            "stage": "llm_call", "round": round_idx,
            "message": f"正在分析（第{round_idx}轮）...",
        })
        round_start = time.perf_counter()
        if run_logger:
            await run_logger.log("llm_call_start", {"round": round_idx})

        try:
            result = await _llm_tools_with_retry(messages, tools_schema, options)
        except (RetryExhaustedError, Exception) as e:
            duration_ms = round((time.perf_counter() - round_start) * 1000, 2)
            diagnostics["llm_rounds"].append({"round": round_idx, "status": "error", "duration_ms": duration_ms})
            diagnostics["errors"].append({"stage": "llm", "message": str(e)})
            logger.error(f"[orchestrator:{trace_id}] LLM 调用失败 (round {round_idx}): {e}")
            if run_logger:
                await run_logger.log("error", {"stage": "llm", "round": round_idx, "message": str(e)})
            yield ("error", {"message": "AI 服务调用失败，请稍后重试。"})
            yield ("done", _done_payload("", failed=True))
            return

        duration_ms = round((time.perf_counter() - round_start) * 1000, 2)
        diagnostics["llm_rounds"].append({
            "round": round_idx,
            "status": "tool_calls" if result.tool_calls else "direct_reply",
            "tool_call_count": len(result.tool_calls),
            "duration_ms": duration_ms,
        })
        report_model_call(
            session_id, f"大模型分析（第{round_idx}轮）", provider=provider,
            model_override=model_override, token_usage=result.usage, duration_ms=duration_ms,
        )
        if result.usage and result.usage.total_tokens:
            last_total_tokens = result.usage.total_tokens
            diagnostics["total_tokens"] = last_total_tokens
            stats["total_tokens"] = last_total_tokens
        if run_logger:
            await run_logger.log("llm_response", {
                "round": round_idx,
                "has_tool_calls": bool(result.tool_calls),
                "tool_call_count": len(result.tool_calls),
                "duration_ms": duration_ms,
            })

        if not result.tool_calls:
            raw_text = result.text or "抱歉，我无法理解您的问题。请尝试换一种方式提问。"
            thinking = _extract_thinking(raw_text)
            text = _strip_think_tags(raw_text)
            if thinking:
                yield ("thinking", {"stage": "reasoning", "text": thinking})
            if text:
                yield ("delta", {"text": text})
            cards = build_cards_from_query_results(query_results)
            if cards:
                yield ("cards", {"cards": [c.model_dump() for c in cards]})
            stats["tool_rounds"] = round_idx - 1
            yield ("done", _done_payload(text))
            return

        # 同一轮只执行一个工具调用（可审计、可回放）
        if len(result.tool_calls) > 1 and run_logger:
            await run_logger.log("note", {
                "message": f"本轮返回 {len(result.tool_calls)} 个工具调用，仅执行第一个",
            })
        tc = result.tool_calls[0]
        tool_name = tc.name
        args = tc.arguments if isinstance(tc.arguments, dict) else {}
        stats["tool_rounds"] = round_idx
        if tool_name not in stats["tools_called"]:
            stats["tools_called"].append(tool_name)

        # ── 闸门 2：步数与循环 ──
        tool_key = f"{tool_name}:{json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)}"
        block_reason: Optional[str] = None
        if tool_name not in CAPABILITY_BY_TOOL:
            block_reason = f"工具 {tool_name} 不在能力目录内，请改用系统提供的智能体工具"
        elif agent_calls >= lim["max_agent_calls"]:
            block_reason = (
                f"智能体调用次数已达上限（{lim['max_agent_calls']} 次），"
                "请基于已有结果直接给出最终答复"
            )
        elif tool_key == last_tool_key:
            block_reason = "重复调用被拦截：与上一步工具和参数完全相同，请更换参数或基于已有结果继续分析"
        elif tool_name == last_tool_name and consecutive_same_agent >= lim["max_consecutive_same_agent"]:
            block_reason = (
                f"已连续调用同一智能体 {consecutive_same_agent} 次，"
                "请换一种查询策略或基于已有数据给出结论"
            )

        if block_reason:
            step = _new_step(_next_step_id(), tool_name, args, status="blocked", error=block_reason)
            steps.append(step)
            yield ("step_started", {"step": step})
            yield ("step_completed", {"step": step})
            report_assistant_event(
                session_id, "step_started", AGENT_TOOL_LABELS.get(tool_name, tool_name), "started",
                f"调用{AGENT_TOOL_LABELS.get(tool_name, tool_name)}", {"step": step},
                started_at=now_iso(), task_id=task_id, step_id=step["step_id"], tool=tool_name,
            )
            report_assistant_event(
                session_id, "step_completed", AGENT_TOOL_LABELS.get(tool_name, tool_name), "failed",
                block_reason[:200], {"step": step},
                started_at=now_iso(), task_id=task_id, step_id=step["step_id"], tool=tool_name,
            )
            diagnostics["tools"].append({"name": tool_name, "status": "blocked", "duration_ms": 0})
            if run_logger:
                await run_logger.log("gate_block", {"round": round_idx, "tool": tool_name, "reason": block_reason})
            messages.append(_assistant_tool_msg(result.text or "", [tc], result.thinking))
            messages.append(_tool_result_msg(tc.id, {"error": block_reason, "intercepted": True}))
            continue

        # ── 闸门 3：写操作确认 ──
        if tool_name == "call_order_agent":
            invalid = validate_tool_input(tool_name, args)
            if invalid:
                step = _new_step(_next_step_id(), tool_name, args, status="blocked", error=f"参数非法：{invalid}")
                steps.append(step)
                yield ("step_started", {"step": step})
                yield ("step_completed", {"step": step})
                report_assistant_event(
                    session_id, "step_started", AGENT_TOOL_LABELS.get(tool_name, tool_name), "started",
                    f"调用{AGENT_TOOL_LABELS.get(tool_name, tool_name)}", {"step": step},
                    started_at=now_iso(), task_id=task_id, step_id=step["step_id"], tool=tool_name,
                )
                report_assistant_event(
                    session_id, "step_completed", AGENT_TOOL_LABELS.get(tool_name, tool_name), "failed",
                    f"参数非法：{invalid}", {"step": step},
                    started_at=now_iso(), task_id=task_id, step_id=step["step_id"], tool=tool_name,
                )
                diagnostics["tools"].append({"name": tool_name, "status": "blocked", "duration_ms": 0})
                if run_logger:
                    await run_logger.log("gate_block", {"round": round_idx, "tool": tool_name, "reason": invalid})
                messages.append(_assistant_tool_msg(result.text or "", [tc], result.thinking))
                messages.append(_tool_result_msg(tc.id, {"error": f"参数非法：{invalid}", "intercepted": True}))
                continue

            step = _new_step(
                _next_step_id(), tool_name, args,
                status="pending_confirmation",
                summary=f"订单 {args.get('order_no')} 写操作等待用户确认",
            )
            steps.append(step)
            yield ("step_started", {"step": step})
            step_start = time.perf_counter()
            old = await query_order_current_fields(
                args.get("order_no") or "", operator_user_id=user_id, trace_id=session_id,
                task_id=task_id, step_id=step["step_id"],
            )
            step["duration_ms"] = round((time.perf_counter() - step_start) * 1000, 2)
            yield ("step_completed", {"step": step})
            report_assistant_event(
                session_id, "step_started", AGENT_TOOL_LABELS.get(tool_name, tool_name), "started",
                f"订单 {args.get('order_no')} 写操作等待用户确认", {"step": step},
                started_at=now_iso(), task_id=task_id, step_id=step["step_id"], tool=tool_name,
            )
            diagnostics["tools"].append({"name": tool_name, "status": "pending_confirmation", "duration_ms": step["duration_ms"]})

            record = await write_confirmation.create_confirmation({
                "session_id": session_id,
                "trace_id": trace_id,
                "task_id": task_id,
                "order_step_id": step["step_id"],
                "next_step_id": step["step_id"] + 1,
                "user_id": user_id,
                "message": message,
                "order_no": args.get("order_no") or "",
                "fields": args.get("fields") or {},
                "old_values": old.get("values") or {},
                "old_values_missing": bool(old.get("missing")),
                "biz_type": "order",
                "action": "update",
                "old_row": old.get("row") or {},
                "model_override": model_override,
            })
            if run_logger:
                await run_logger.log("confirmation_created", {
                    "confirmation_id": record["confirmation_id"],
                    "task_id": task_id,
                    "order_no": record["order_no"],
                    "fields": record["fields"],
                    "old_values": record["old_values"],
                })
            confirmation_payload = {
                "confirmation_id": record["confirmation_id"],
                "order_no": record["order_no"],
                "fields": [
                    {"field": f, "old_value": record["old_values"].get(f), "new_value": record["fields"].get(f)}
                    for f in record["fields"]
                ],
                "created_at": record["created_at"],
                "expires_at": record["expires_at"],
                "status": "pending",
            }
            report_assistant_event(
                session_id, "confirmation_required", "写操作确认", "started",
                f"订单 {record['order_no']} 写操作待用户确认",
                {
                    "confirmationId": record["confirmation_id"],
                    "orderNo": record["order_no"],
                    "fields": [
                        {"field": f, "oldValue": record["old_values"].get(f), "newValue": record["fields"].get(f)}
                        for f in record["fields"]
                    ],
                    "expiresAt": record["expires_at"],
                },
                started_at=now_iso(),
                task_id=task_id, step_id=step["step_id"], tool=tool_name,
                confirmation_id=record["confirmation_id"],
            )
            pre_text = _strip_think_tags(result.text or "") or (
                "检测到订单写操作，已生成确认单：请核对「旧值 → 新值」后确认执行或取消。"
            )
            if pre_text:
                yield ("delta", {"text": pre_text})
            yield ("confirmation_required", confirmation_payload)
            yield ("done", _done_payload(pre_text, confirmation=confirmation_payload))
            return

        # ── 只读工具直接执行 ──
        step = _new_step(_next_step_id(), tool_name, args, status="running", summary=_step_summary(tool_name, args))
        steps.append(step)
        yield ("step_started", {"step": step})
        report_assistant_event(
            session_id, "step_started", AGENT_TOOL_LABELS.get(tool_name, tool_name), "started",
            f"调用{AGENT_TOOL_LABELS.get(tool_name, tool_name)}", {"step": step},
            started_at=now_iso(), task_id=task_id, step_id=step["step_id"], tool=tool_name,
        )
        tool_start = time.perf_counter()
        outcome = await execute_agent_tool(
            tool_name, args, operator_user_id=user_id, trace_id=session_id,
            task_id=task_id, step_id=step["step_id"],
        )
        duration_ms = round((time.perf_counter() - tool_start) * 1000, 2)
        step["duration_ms"] = duration_ms
        if outcome.get("ok"):
            step["status"] = "completed"
            step["item_count"] = outcome.get("item_count")
            gap_info = None
            if tool_name == "call_query_agent" and gap_notify:
                gap_info = await _check_query_gaps(
                    args, outcome.get("result") or {}, user_id
                )
            trimmed = trim_result(
                outcome.get("result") or {},
                max_items=lim["trim_max_items"], max_chars=lim["trim_max_chars"],
            )
            if gap_info is not None:
                trimmed = {**trimmed, "completeness": gap_info}
            if tool_name == "call_query_agent":
                query_results.append({"path": args.get("path"), "data": outcome.get("result") or {}})
        else:
            step["status"] = "failed"
            step["error"] = outcome.get("error")
            trimmed = {"error": outcome.get("error")}
        yield ("step_completed", {"step": step})
        report_assistant_event(
            session_id, "step_completed", AGENT_TOOL_LABELS.get(tool_name, tool_name),
            "completed" if step["status"] == "completed" else "failed",
            step["summary"], {"step": step}, started_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step["step_id"], tool=tool_name,
        )
        diagnostics["tools"].append({"name": tool_name, "status": step["status"], "duration_ms": duration_ms})
        if run_logger:
            await run_logger.log("tool_call", {
                "round": round_idx,
                "step": step,
                "success": outcome.get("ok"),
            })

        agent_calls += 1
        consecutive_same_agent = consecutive_same_agent + 1 if tool_name == last_tool_name else 1
        last_tool_name = tool_name
        last_tool_key = tool_key

        messages.append(_assistant_tool_msg(result.text or "", [tc], result.thinking))
        messages.append(_tool_result_msg(tc.id, trimmed))

    # 循环耗尽 → 强制收尾总结
    partial_reason = "智能体调用轮数已达上限，返回已完成步骤"
    if run_logger:
        await run_logger.log("note", {"message": partial_reason})
    messages.append(ChatMessage(
        role="user",
        content="（系统提示：已达到最大执行步数，请基于以上已有结果直接给出最终答复，不要继续调用工具。）",
    ))
    try:
        text, thinking = await _final_answer_text(
            messages, options, session_id=session_id, provider_name=provider,
            model_override=model_override, stream_final=stream_final, label="生成总结",
        )
    except Exception as e:
        logger.error(f"[orchestrator:{trace_id}] 最终总结失败: {e}")
        text, thinking = "查询完成，但生成总结时出现问题。", []
    for t in thinking:
        yield ("thinking", {"stage": "reasoning", "text": t})
    if text:
        yield ("delta", {"text": text})
    cards = build_cards_from_query_results(query_results)
    if cards:
        yield ("cards", {"cards": [c.model_dump() for c in cards]})
    yield ("done", _done_payload(text, partial=True, partial_reason=partial_reason))


async def _append_session_note(session_id: str, text: str) -> None:
    if not session_id or not text:
        return
    try:
        await session_store.append_messages(session_id, [{"role": "assistant", "content": text}])
    except Exception as e:
        logger.warning(f"回填会话失败: {e}")


async def _notify_write_result(
    *, record: Dict[str, Any], write_result: Any, fields: Dict[str, Any],
    biz_type: str, action: str, biz_no: str, operator_user_id: str,
) -> None:
    try:
        effective_biz_no = str(biz_no or "").strip()
        if action == "create" and not effective_biz_no and isinstance(write_result, dict):
            effective_biz_no = str(
                write_result.get("order_no") or write_result.get("biz_no") or ""
            ).strip()
        report_assistant_event(
            str(record.get("trace_id") or ""),
            "note", "助手通知", "info",
            f"{biz_type} {effective_biz_no} {action} 通知已调度",
            {"bizType": biz_type, "bizNo": effective_biz_no, "action": action},
            started_at=now_iso(),
            task_id=record.get("task_id") or None,
            step_id=record.get("order_step_id"),
            tool="assistant_notify",
            confirmation_id=record.get("confirmation_id"),
        )
        notify_agent_change(
            biz_type=biz_type, biz_no=effective_biz_no, action=action,
            operator_user_id=operator_user_id,
        )
        if action == "delete":
            return
        if action == "update" and record.get("old_values_missing"):
            logger.info("gap_skip reason=untrusted biz_type=%s biz_no=%s",
                        biz_type, effective_biz_no)
            return
        if action == "create":
            values = dict(record.get("payload") or record.get("fields") or {})
            if isinstance(write_result, dict):
                values = {**values, **write_result}
        else:
            old_row = record.get("old_row") or {}
            if not old_row:
                logger.info("gap_skip reason=untrusted biz_type=%s biz_no=%s",
                            biz_type, effective_biz_no)
                return
            values = {**old_row, **fields}
        if not values:
            logger.info("gap_skip reason=untrusted biz_type=%s biz_no=%s",
                        biz_type, effective_biz_no)
            return
        missing = await _gap_missing(
            biz_type=biz_type, biz_no=effective_biz_no, values=values
        )
        if missing:
            _schedule_gap_notify(
                biz_type=biz_type, biz_no=effective_biz_no, missing=missing,
                initiator_user_id=operator_user_id,
            )
    except Exception as e:
        logger.warning("notify write result failed biz_type=%s biz_no=%s: %s",
                       biz_type, biz_no, e)


async def resolve_confirmation(
    db: Any,
    confirmation_id: str,
    action: str,
    current_user_id: str,
) -> Dict[str, Any]:
    """确认 / 取消写操作确认单。

    confirm：原子消费 → 派单订单智能体（不重试）→ 回填对话 → 只读续跑 ReAct 生成回查总结；
    cancel：原子消费后丢弃，不产生任何写入。
    返回 {"code", "message", "data"?}，由路由直接返回。
    """
    record = await write_confirmation.consume_confirmation(confirmation_id)
    if not record:
        return {"code": 404, "message": "确认单不存在、已处理或已过期"}

    record_user = str(record.get("user_id") or "")
    if record_user and str(current_user_id or "") and record_user != str(current_user_id):
        return {"code": 403, "message": "只有发起该写操作的用户才能确认或取消"}

    session_id = str(record.get("session_id") or "")
    trace_id = str(record.get("trace_id") or "")
    task_id = str(record.get("task_id") or "")
    order_step_id = int(record.get("order_step_id") or 0)
    order_no = record.get("order_no") or ""
    fields = record.get("fields") or {}
    old_values = record.get("old_values") or {}
    biz_type = str(record.get("biz_type") or "order")
    write_action = str(record.get("action") or "update")
    fields_payload = [
        {"field": f, "old_value": old_values.get(f), "new_value": fields.get(f)}
        for f in fields
    ]

    if action == "cancel":
        report_assistant_event(
            session_id, "step_completed", "订单智能体", "info",
            f"订单 {order_no} 写操作已取消，未产生写入", {"confirmationId": confirmation_id},
            started_at=now_iso(),
            task_id=task_id, step_id=order_step_id, tool="call_order_agent",
            confirmation_id=confirmation_id,
        )
        report_assistant_event(
            session_id, "confirmation_resolved", "写操作确认", "info",
            f"用户取消写操作（订单 {order_no}），未产生写入", {"confirmationId": confirmation_id},
            started_at=now_iso(),
            task_id=task_id, step_id=order_step_id, tool="call_order_agent",
            confirmation_id=confirmation_id,
        )
        cancel_text = f"已取消订单 {order_no} 的写操作，订单未做任何修改。"
        await _append_session_note(session_id, cancel_text)
        report_assistant_event(
            session_id, "assistant_reply", "助手回复", "completed",
            f"回复：{cancel_text}", {"intent": "agent", "length": len(cancel_text)},
            started_at=now_iso(),
        )
        return {
            "code": 0,
            "message": "已取消，未执行任何写入",
            "data": {
                "confirmation": {
                    "confirmation_id": confirmation_id,
                    "order_no": order_no,
                    "fields": fields_payload,
                    "status": "cancelled",
                },
                "reply": {
                    "text": cancel_text,
                    "cards": [],
                    "steps": [],
                    "provider": "system",
                },
            },
        }

    # 执行写入（不重试）
    started_at = now_iso()
    start = time.perf_counter()
    report_assistant_event(
        session_id, "tool_call", "call_order_agent", "started",
        f"调用订单智能体写入订单 {order_no}", {"fields": fields}, started_at=started_at,
        task_id=task_id, step_id=order_step_id, tool="call_order_agent",
        confirmation_id=confirmation_id,
    )
    dispatch = await call_agent_run(
        AGENT_SPECS["order"],
        {"order_no": order_no, "fields": fields},
        timeout=TOOL_TIMEOUT_S["call_order_agent"],
        operator_user_id=record_user or current_user_id,
    )
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    if not dispatch.get("online"):
        error = f"订单智能体不可用：{dispatch.get('reason')}"
    elif dispatch.get("busy"):
        error = f"订单智能体繁忙：{dispatch.get('reason')}"
    elif not dispatch.get("ok"):
        error = f"写操作失败：{dispatch.get('reason')}"
    else:
        error = None
    write_result = None if error else dispatch.get("result")
    report_assistant_event(
        session_id, "tool_result", "call_order_agent",
        "completed" if error is None else "failed",
        (error or f"订单 {order_no} 写入成功")[:200], {"fields": fields},
        started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
        task_id=task_id, step_id=order_step_id, tool="call_order_agent",
        confirmation_id=confirmation_id,
    )
    report_assistant_event(
        session_id, "step_completed", "订单智能体",
        "completed" if error is None else "failed",
        f"订单 {order_no} 写操作结果", {"confirmationId": confirmation_id, "error": error},
        started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
        task_id=task_id, step_id=order_step_id, tool="call_order_agent",
        confirmation_id=confirmation_id,
    )
    report_assistant_event(
        session_id, "confirmation_resolved", "写操作确认",
        "completed" if error is None else "failed",
        f"确认执行结果：{error or '写入成功'}", {"confirmationId": confirmation_id},
        started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
        task_id=task_id, step_id=order_step_id, tool="call_order_agent",
        confirmation_id=confirmation_id,
    )

    confirmation_info = {
        "confirmation_id": confirmation_id,
        "order_no": order_no,
        "fields": fields_payload,
        "status": "executed" if error is None else "failed",
        "write_result": write_result,
        "error": error,
    }
    if error:
        await _append_session_note(session_id, f"写操作执行失败：{error}")
        return {"code": 0, "message": error, "data": {"confirmation": confirmation_info, "reply": None}}

    await _notify_write_result(
        record=record, write_result=write_result, fields=fields,
        biz_type=biz_type, action=write_action, biz_no=order_no,
        operator_user_id=record_user or current_user_id,
    )

    # 回填对话 + 只读续跑：回查验证与总结
    try:
        rt = await get_scope_config(db, ASSISTANT_SCOPE)
    except Exception as e:
        logger.warning(f"[orchestrator] 续跑读取配置失败，使用默认值: {e}")
        from app.services.ai_config import ASSISTANT_CONFIG_DEFS
        rt = {k: d.default for k, d in ASSISTANT_CONFIG_DEFS.items()}
    disabled = set(rt.get("disabled_tools") or [])
    system_prompt = resolve_system_prompt(rt.get("system_prompt"), disabled)
    model_override = (rt.get("model_name") or "").strip() or None
    history = await session_store.get_history(session_id)
    continuation = (
        f"用户已确认执行写操作。订单智能体执行结果："
        f"{json.dumps(write_result, ensure_ascii=False, default=str)}。"
        "请回查验证订单字段是否已按预期修改，并给出简要总结。"
    )

    run_logger: Optional[RunLogger] = None
    if trace_id:
        try:
            run_logger = RunLogger(trace_id=trace_id, session_id=session_id, user_id=record_user)
        except Exception as e:
            logger.warning(f"[orchestrator] 续跑 RunLogger 初始化失败: {e}")

    text, cards, steps_out = "", [], []
    try:
        async for event, data in run_reaction(
            continuation, history,
            system_prompt=system_prompt, model_override=model_override,
            temperature=rt.get("temperature", 0.1), max_tokens=rt.get("max_tokens", 4096),
            max_tool_rounds=rt.get("max_tool_rounds", 6), max_agent_calls=rt.get("max_agent_calls", 8),
            disabled_tools=disabled, session_id=session_id, trace_id=trace_id,
            user_id=record_user, run_logger=run_logger,
            provider_name=ai_service.current_provider(),
            limits=CONTINUATION_LIMITS, include_order_tool=False, stream_final=False,
            task_id=task_id, step_id_base=order_step_id,
            gap_notify=False,
        ):
            if event == "delta":
                text += data.get("text") or ""
            elif event == "cards":
                cards = data.get("cards") or []
            elif event == "done":
                steps_out = data.get("steps") or []
    except Exception as e:
        logger.warning(f"[orchestrator] 确认后续跑失败: {e}")
        text = ""
    finally:
        if run_logger:
            try:
                await run_logger.close()
            except Exception as e:
                logger.warning(f"[orchestrator] 续跑 RunLogger 关闭失败: {e}")

    final_text = text or f"写操作已执行：订单 {order_no} 已更新字段 {', '.join(fields)}。"
    await _append_session_note(session_id, final_text)
    return {
        "code": 0,
        "message": "写操作已执行",
        "data": {
            "confirmation": confirmation_info,
            "reply": {
                "text": final_text,
                "cards": cards,
                "steps": steps_out,
                "provider": ai_service.current_provider(),
            },
        },
    }
