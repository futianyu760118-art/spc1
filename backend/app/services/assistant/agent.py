"""单层 Agent — LLM + Tool Calling 循环，含摘要、重试、日志、取消、思考过程透传"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ai import ai_service, ChatMessage, ChatOptions, NotSupportedError
from app.services.ai_config import (
    ASSISTANT_CONFIG_DEFS,
    ASSISTANT_SCOPE,
    get_scope_config,
    render_system_prompt,
)
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
from app.services.assistant.hub_reporter import now_iso, report_assistant_event, report_model_call
from app.services.assistant.context_manager import (
    estimate_tokens,
    should_summarize,
    summarize_round,
    build_compressed_messages,
    fallback_sliding_window,
    render_messages_for_summary,
)
from app.schemas.assistant.schemas import AssistantReply

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

TOOL_RETRY_CONFIG = RetryConfig(
    enabled=True,
    max_retries=1,
    initial_delay=0.5,
    exponential_base=2.0,
    max_delay=2.0,
    retryable_exceptions=(asyncio.TimeoutError, ConnectionError),
)

async def _load_runtime_config(db: AsyncSession) -> Dict[str, Any]:
    """每次请求读 DB 配置（无缓存，多实例强一致）；读失败回退默认值不阻断对话"""
    try:
        return await get_scope_config(db, ASSISTANT_SCOPE)
    except Exception as e:
        logger.warning(f"[agent] 读取运行时配置失败，使用默认值: {e}")
        return {k: d.default for k, d in ASSISTANT_CONFIG_DEFS.items()}

INTENT_RECOGNITION_PROMPT = """你是一个意图识别助手。分析用户的消息，判断用户的意图类型。

意图类型：
1. QUERY_DATA - 需要查询系统数据或获取行动建议（需要调用工具）
   示例：
   - "查询订单HJ202604-0018-0086的信息"
   - "有哪些逾期的订单？"
   - "显示所有高风险订单"
   - "供应商XX的采购订单有哪些？"
   - "今天有什么需要关注的？"
   - "给我今日简报"
   - "采购有什么风险？"
   - "这个订单该怎么跟进？"
   - "本周总结"
   - "订单HJ202604-0018-0086齐套了吗？"
   - "查一下这个订单的欠料情况"
   - "物料编码XX的BOM是什么？"
   - "查一下这个产品的BOM明细"

2. ANALYZE_HISTORY - 仅分析聊天历史中已有的数据（不需要调用工具）
   示例：
   - "帮我分析一下这些订单的风险分布"
   - "总结一下上面的数据"
   - "这些订单有什么共同特点？"
   - "对比一下刚才查到的两个订单"
   - "计算一下平均交期"

3. GENERAL_CHAT - 一般对话（不需要调用工具）
   示例：
   - "你好"
   - "谢谢"
   - "你能做什么？"

判断规则：
- 如果用户明确提到要"查询"、"搜索"、"显示"、"找"某个具体的订单号、供应商、物料等，判断为 QUERY_DATA
- 如果用户询问"该做什么"、"需要关注什么"、"有什么建议"、"简报"、"预警"、"跟进建议"，判断为 QUERY_DATA
- 如果用户提到"齐套"、"欠料"、"BOM"、"物料清单"、"配方"并要求查询，判断为 QUERY_DATA
- 如果用户使用"这些"、"上面"、"刚才"、"以上"等指代词，且要求分析、总结、对比，判断为 ANALYZE_HISTORY
- 如果用户要求对已有数据进行计算、统计、分析，判断为 ANALYZE_HISTORY
- 其他情况判断为 GENERAL_CHAT

请只返回意图类型（QUERY_DATA、ANALYZE_HISTORY 或 GENERAL_CHAT），不要有其他内容。"""

SYSTEM_PROMPT = """你是供应链与生产协同中台的智能决策助手。你不仅能查询数据，还能基于数据分析给出行动建议和决策支持。

可用工具：
- search_orders: 搜索销售订单（支持按订单号、客户、风险等级、状态、交期、是否逾期等条件，返回完整的订单信息）
- search_purchase_orders: 搜索采购订单PO（支持按PO号、关联销售订单号、供应商、物料等条件）
- search_materials: 搜索物料需求/问题物料/长交期物料
- search_kit_analysis: 查询订单齐套信息（根据订单号查齐套率、已到齐/部分到/未下单/逾期/呆滞物料数量及物料明细）
- search_bom_details: 查询产品BOM明细（根据物料编码查BOM列表及明细行：子物料、用量、损耗率、工序等）
- search_production: 搜索生产工序进度和工序异常
- search_run_orders: 搜索跑单管理记录
- search_exceptions: 搜索风险问题/品质异常/问题日志/变更日志
- search_invoices: 搜索采购开票和供应商付款记录
- search_eta_updates: 搜索交期变更(ETA)记录
- search_basicdata: 搜索客户/供应商/物料
- search_users: 搜索系统用户
- get_dashboard_summary: 获取驾驶舱概览（今日/本周/本月交付统计）
- suggest_actions: 生成行动建议（每日简报、订单跟进、采购预警、周总结）

编号识别规则：
- HJ开头的编号（如HJ202604-0018-0086）是销售订单号，查采购订单时用 order_no 参数
- PO开头或纯数字编号通常是采购订单号，用 po_no 参数
- 用户提到具体编号时，优先使用精确匹配参数（order_no/po_no），而非 keyword

查询策略：
1. 如果用户想了解某个订单，用 search_orders 的 order_no 参数精确查询，会返回完整的订单信息
2. 如果需要查某订单的采购情况，用 search_purchase_orders 的 order_no 参数
3. 如果用户问某订单的齐套情况（如"齐套了吗""欠什么料""物料到齐没有"），用 search_kit_analysis 的 order_no 参数
4. 如果用户问某产品的BOM/物料清单/配方（如"XX物料编码的BOM""查一下这个产品的明细"），用 search_bom_details 的 material_code 参数
5. 可以一次调用多个工具来获取完整信息
6. 查询结果为空时如实告知，不要虚构数据

决策支持策略：
1. 当用户问"今天该做什么"、"有什么需要关注的"时，调用 suggest_actions 的 daily_briefing 场景
2. 当用户问某个订单的跟进建议时，调用 suggest_actions 的 order_followup 场景
3. 当用户关心采购风险时，调用 suggest_actions 的 procurement_alert 场景
4. 当用户要周总结时，调用 suggest_actions 的 weekly_summary 场景
5. 在回复中主动给出优先级排序和具体行动建议，而不仅仅列出数据

回复格式要求（严格遵守）：
- 使用简洁的 Markdown 格式输出
- 用 **加粗** 标注关键信息（订单号、数量、日期、风险等级）
- 多条数据用有序列表（1. 2. 3.）或表格呈现，不要用无序列表嵌套无序列表
- 表格格式示例：
  | 订单号 | 客户 | 交期 | 状态 |
  |--------|------|------|------|
  | HJ... | XX公司 | 2025-06-01 | 逾期 |
- 行动建议用如下格式：
  **🔴 紧急** 描述内容
  **🟡 重要** 描述内容
  **🔵 关注** 描述内容
- 段落之间空一行，保持视觉清晰
- 不要输出过长的内容，控制在 500 字以内
- 不要重复工具返回的原始 JSON 数据
- 不要使用 HTML 标签
- 不要输出 <think> 标签或思考过程
"""

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


def _check_cancelled(session_id: str, run_logger: Optional[RunLogger]) -> bool:
    if not session_id:
        return False
    if CancellationRegistry.is_cancelled(session_id):
        reason = CancellationRegistry.reason(session_id)
        logger.info(f"[agent] session={session_id} 已被取消, reason={reason}")
        if run_logger:
            asyncio.create_task(run_logger.log("cancel", {"reason": reason}))
        return True
    return False


@async_retry(LLM_RETRY_CONFIG)
async def _intent_chat_with_retry(messages: List[ChatMessage], options: ChatOptions) -> str:
    return await ai_service.chat(messages, options)


@async_retry(LLM_RETRY_CONFIG)
async def _llm_chat_with_retry(messages: List[ChatMessage], options: ChatOptions) -> str:
    return await ai_service.chat(messages, options)


@async_retry(LLM_RETRY_CONFIG)
async def _llm_tools_with_retry(messages: List[ChatMessage], tools: List[dict], options: ChatOptions):
    return await ai_service.chat_with_tools(messages, tools, options)


async def _recognize_intent(
    message: str,
    history: List[Dict[str, Any]],
    intent_prompt: Optional[str] = None,
) -> str:
    try:
        messages = [ChatMessage(role="system", content=intent_prompt or INTENT_RECOGNITION_PROMPT)]
        recent_history = history[-6:] if len(history) > 6 else history
        for msg in recent_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
        messages.append(ChatMessage(role="user", content=message))

        options = ChatOptions(temperature=0.0, max_tokens=50, timeout=10)
        result = await _intent_chat_with_retry(messages, options)
        intent = result.strip().upper()
        if "QUERY_DATA" in intent:
            return "QUERY_DATA"
        elif "ANALYZE_HISTORY" in intent:
            return "ANALYZE_HISTORY"
        elif "GENERAL_CHAT" in intent:
            return "GENERAL_CHAT"
        logger.warning(f"无法识别意图，返回值: {result}，默认为 QUERY_DATA")
        return "QUERY_DATA"
    except Exception as e:
        logger.error(f"意图识别失败: {e}，默认为 QUERY_DATA")
        return "QUERY_DATA"


async def _execute_tool_with_retry(
    db: AsyncSession,
    tool_name: str,
    params: Dict[str, Any],
    timeout: int = TOOL_EXECUTE_TIMEOUT,
    disabled_tools: Optional[set] = None,
    trace_id: str = "",
) -> Dict[str, Any]:
    from app.services.assistant.tool_registry import get_tool

    if disabled_tools and tool_name in disabled_tools:
        report_assistant_event(trace_id, "tool_result", tool_name, "failed", f"工具 {tool_name} 已被管理员禁用")
        return {"error": f"工具 {tool_name} 已被管理员禁用"}
    tool_def = get_tool(tool_name)
    if not tool_def:
        report_assistant_event(trace_id, "tool_result", tool_name, "failed", f"工具 {tool_name} 不存在")
        return {"error": f"工具 {tool_name} 不存在"}

    started_at = now_iso()
    report_assistant_event(
        trace_id, "tool_call", tool_name, "started",
        f"调用工具 {tool_name}", {"params": params}, started_at=started_at,
    )
    loop_start = time.perf_counter()

    last_error: Optional[Exception] = None
    for attempt in range(TOOL_RETRY_CONFIG.max_retries + 1):
        try:
            data = await asyncio.wait_for(
                tool_def.execute(db, params),
                timeout=timeout,
            )
            item_count = data.get("total", 0) if isinstance(data, dict) else 0
            report_assistant_event(
                trace_id, "tool_result", tool_name, "completed",
                f"返回 {item_count} 条",
                {"itemCount": item_count, "attempts": attempt + 1},
                started_at=started_at, ended_at=now_iso(),
                duration_ms=round((time.perf_counter() - loop_start) * 1000, 2),
            )
            return data
        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning(f"工具 {tool_name} 执行超时 (attempt {attempt + 1})")
        except TOOL_RETRY_CONFIG.retryable_exceptions as e:
            last_error = e
            logger.warning(f"工具 {tool_name} 执行失败 (attempt {attempt + 1}): {e}")

        if attempt < TOOL_RETRY_CONFIG.max_retries:
            await asyncio.sleep(TOOL_RETRY_CONFIG.calculate_delay(attempt))

    report_assistant_event(
        trace_id, "tool_result", tool_name, "failed",
        f"工具执行失败：{last_error}"[:200],
        {"attempts": TOOL_RETRY_CONFIG.max_retries + 1},
        started_at=started_at, ended_at=now_iso(),
        duration_ms=round((time.perf_counter() - loop_start) * 1000, 2),
    )
    return {"error": f"工具 {tool_name} 执行失败: {str(last_error)}"}


async def _maybe_summarize(
    messages: List[Any],
    run_logger: Optional[RunLogger],
    session_id: str = "",
) -> List[Any]:
    settings = get_settings()
    if not settings.AI_SUMMARY_ENABLED:
        return messages

    local_tokens = estimate_tokens(messages)
    api_total_tokens: Optional[int] = None

    if should_summarize(local_tokens, api_total_tokens, settings.AI_SUMMARY_TOKEN_LIMIT, True):
        if run_logger:
            await run_logger.log("summary_trigger", {
                "local_tokens": local_tokens,
                "api_total_tokens": api_total_tokens,
                "threshold": settings.AI_SUMMARY_TOKEN_LIMIT,
                "message_count": len(messages),
            })

        rendered = render_messages_for_summary(messages)
        user_indices = [i for i, m in enumerate(rendered) if m.get("role") == "user" and i > 0]
        if len(user_indices) < 2:
            return messages

        system_msg = next((m for m in rendered if m.get("role") == "system"), None)
        chat_fn = ai_service.chat

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
                logger.warning(f"[agent] 摘要轮次 {i + 1} 失败: {e}")

        if summaries:
            new_messages_dict = build_compressed_messages(rendered, system_msg, summaries)
            new_messages: List[ChatMessage] = []
            for m in new_messages_dict:
                cm = ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
                new_messages.append(cm)
            if run_logger:
                await run_logger.log("summary_done", {
                    "rounds_summarized": len(summaries),
                    "before_count": len(messages),
                    "after_count": len(new_messages),
                    "before_tokens": local_tokens,
                })
            return new_messages
        else:
            fallback = fallback_sliding_window(rendered, keep_last=6)
            if run_logger:
                await run_logger.log("summary_fallback", {
                    "reason": "summarization_failed",
                    "before_count": len(messages),
                    "after_count": len(fallback),
                })
            new_messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in fallback]
            return new_messages

    return messages


async def run(
    message: str,
    db: AsyncSession,
    session_id: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    trace_id: str = "",
    user_id: str = "",
) -> AssistantReply:
    """运行 Agent：单层 LLM + Tool Calling 循环"""

    settings = get_settings()
    provider_name = ai_service.current_provider()

    rt = await _load_runtime_config(db)
    disabled = set(rt.get("disabled_tools") or [])
    system_prompt = render_system_prompt(rt.get("system_prompt") or SYSTEM_PROMPT, disabled)
    intent_prompt = (rt.get("intent_prompt") or "").strip() or None
    main_options = ChatOptions(
        temperature=rt.get("temperature", 0.1),
        max_tokens=rt.get("max_tokens", 4096),
        model=(rt.get("model_name") or "").strip() or None,
    )

    diagnostics: Dict[str, Any] = {
        "provider": provider_name,
        "path": "agent",
        "fallback": False,
        "intent": None,
        "llm_rounds": [],
        "tools": [],
        "errors": [],
    }

    run_logger: Optional[RunLogger] = None
    if trace_id:
        try:
            run_logger = RunLogger(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"[agent:{trace_id}] 初始化 RunLogger 失败: {e}")

    if session_id:
        await CancellationRegistry.get_or_create(session_id)

    try:
        if run_logger:
            await run_logger.log("request", {
                "message": message[:500],
                "provider": provider_name,
            })

        if provider_name == "rule_based":
            if run_logger:
                await run_logger.log("error", {"stage": "init", "message": "AI provider unavailable"})
            return AssistantReply(
                intent="unknown",
                text="AI 服务暂不可用，请联系管理员配置 AI 服务。",
                suggestions=[],
                provider="rule_based",
            )

        if _check_cancelled(session_id, run_logger):
            return AssistantReply(
                text="对话已取消。",
                provider=provider_name,
            )

        history = conversation_history or []
        if session_id and not history:
            history = await session_store.get_history(session_id)

        if run_logger:
            await run_logger.log("intent_start", {"message_preview": message[:200]})

        intent_started = now_iso()
        intent_start = time.perf_counter()
        intent = await _recognize_intent(message, history, intent_prompt)
        report_model_call(
            session_id, "意图识别", provider=provider_name,
            started_at=intent_started,
            duration_ms=round((time.perf_counter() - intent_start) * 1000, 2),
        )
        diagnostics["intent"] = intent
        logger.info(f"[agent:{trace_id}] 意图识别结果: {intent}")

        if run_logger:
            await run_logger.log("intent_done", {"intent": intent})

        if intent in ("ANALYZE_HISTORY", "GENERAL_CHAT"):
            messages: List[Any] = [ChatMessage(role="system", content=system_prompt)]
            for msg in history[-10:]:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append(ChatMessage(role=role, content=content))
            messages.append(ChatMessage(role="user", content=message))

            messages = await _maybe_summarize(messages, run_logger, session_id)

            try:
                options = ChatOptions(temperature=main_options.temperature, max_tokens=main_options.max_tokens, model=main_options.model, timeout=60)
                chat_started = now_iso()
                chat_start = time.perf_counter()
                result = await _llm_chat_with_retry(messages, options)
                report_model_call(
                    session_id, "生成回复", provider=provider_name,
                    model_override=main_options.model, started_at=chat_started,
                    duration_ms=round((time.perf_counter() - chat_start) * 1000, 2),
                )
                raw_text = result if isinstance(result, str) else (result.text or "")
                thinking = _extract_thinking(raw_text)
                text = _strip_think_tags(raw_text)

                if run_logger:
                    await run_logger.log("llm_response", {
                        "intent": intent,
                        "text_length": len(text),
                        "thinking_length": len(thinking),
                    })

                reply = AssistantReply(
                    intent=intent.lower(),
                    text=text,
                    thinking=thinking if thinking else None,
                    cards=[],
                    suggestions=[],
                    provider=provider_name,
                    diagnostics=diagnostics,
                )

                await _save_conversation(session_id, message, text)
                return reply

            except Exception as e:
                logger.error(f"[agent:{trace_id}] LLM 调用失败: {e}")
                diagnostics["errors"].append({"stage": "llm", "message": str(e)})
                if run_logger:
                    await run_logger.log("error", {"stage": "llm", "message": str(e)})
                return AssistantReply(
                    text="AI 服务调用失败，请稍后重试。",
                    suggestions=[],
                    provider=provider_name,
                )

        tools_schema = get_openai_tools_schema(exclude=disabled)
        if not tools_schema:
            return AssistantReply(text="系统未注册任何工具，请联系管理员。")

        messages = [ChatMessage(role="system", content=system_prompt)]
        for msg in history[-10:]:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
        messages.append(ChatMessage(role="user", content=message))

        messages = await _maybe_summarize(messages, run_logger, session_id)

        all_tool_results: List[Dict[str, Any]] = []
        options = ChatOptions(temperature=main_options.temperature, max_tokens=main_options.max_tokens, model=main_options.model, timeout=120)
        last_api_total_tokens: Optional[int] = None

        for round_idx in range(rt.get("max_tool_rounds", MAX_TOOL_ROUNDS)):
            if _check_cancelled(session_id, run_logger):
                return AssistantReply(
                    text="对话已取消。",
                    provider=provider_name,
                    diagnostics=diagnostics,
                )

            round_start = time.perf_counter()
            if run_logger:
                await run_logger.log("llm_call_start", {"round": round_idx + 1})

            try:
                result = await _llm_tools_with_retry(messages, tools_schema, options)
            except RetryExhaustedError as e:
                duration_ms = round((time.perf_counter() - round_start) * 1000, 2)
                diagnostics["llm_rounds"].append({
                    "round": round_idx + 1, "status": "error", "duration_ms": duration_ms,
                })
                diagnostics["errors"].append({"stage": "llm", "message": str(e)})
                logger.error(f"[agent:{trace_id}] LLM 调用重试耗尽 (round {round_idx + 1}): {e}")
                if run_logger:
                    await run_logger.log("error", {"stage": "llm_retry_exhausted", "round": round_idx + 1, "message": str(e)})
                return AssistantReply(
                    text="AI 服务调用失败，请稍后重试。",
                    suggestions=[],
                    provider=provider_name,
                )
            except Exception as e:
                duration_ms = round((time.perf_counter() - round_start) * 1000, 2)
                diagnostics["llm_rounds"].append({
                    "round": round_idx + 1, "status": "error", "duration_ms": duration_ms,
                })
                diagnostics["errors"].append({"stage": "llm", "message": str(e)})
                logger.error(f"[agent:{trace_id}] LLM 调用失败 (round {round_idx + 1}): {e}")
                if run_logger:
                    await run_logger.log("error", {"stage": "llm", "round": round_idx + 1, "message": str(e)})
                return AssistantReply(
                    text="AI 服务调用失败，请稍后重试。",
                    suggestions=[],
                    provider=provider_name,
                )

            duration_ms = round((time.perf_counter() - round_start) * 1000, 2)
            diagnostics["llm_rounds"].append({
                "round": round_idx + 1,
                "status": "tool_calls" if result.tool_calls else "direct_reply",
                "tool_call_count": len(result.tool_calls),
                "duration_ms": duration_ms,
            })
            report_model_call(
                session_id, f"大模型分析（第{round_idx + 1}轮）", provider=provider_name,
                model_override=main_options.model, token_usage=result.usage,
                duration_ms=duration_ms,
            )

            if result.usage and result.usage.total_tokens:
                last_api_total_tokens = result.usage.total_tokens
                diagnostics["total_tokens"] = last_api_total_tokens

            if run_logger:
                await run_logger.log("llm_response", {
                    "round": round_idx + 1,
                    "has_tool_calls": bool(result.tool_calls),
                    "tool_call_count": len(result.tool_calls),
                    "duration_ms": duration_ms,
                    "usage": {
                        "prompt_tokens": result.usage.prompt_tokens if result.usage else 0,
                        "completion_tokens": result.usage.completion_tokens if result.usage else 0,
                        "total_tokens": result.usage.total_tokens if result.usage else 0,
                    } if result.usage else None,
                })

            if not result.tool_calls:
                raw_text = result.text or "抱歉，我无法理解您的问题。请尝试换一种方式提问。"
                thinking = _extract_thinking(raw_text)
                text = _strip_think_tags(raw_text)
                reply = _build_reply(text, all_tool_results, diagnostics, message)
                reply.thinking = thinking if thinking else None
                await _save_conversation(session_id, message, text)
                if run_logger:
                    await run_logger.log("done", {
                        "intent": "agent",
                        "text_length": len(text),
                        "tool_count": len(all_tool_results),
                    })
                return reply

            tool_messages = []
            for tc in result.tool_calls:
                tool_start = time.perf_counter()
                data = await _execute_tool_with_retry(db, tc.name, tc.arguments, timeout=rt.get("tool_execute_timeout", TOOL_EXECUTE_TIMEOUT), disabled_tools=disabled, trace_id=session_id)
                tool_duration = round((time.perf_counter() - tool_start) * 1000, 2)

                has_error = "error" in data
                diagnostics["tools"].append({
                    "name": tc.name,
                    "status": "error" if has_error else "success",
                    "duration_ms": tool_duration,
                })

                if run_logger:
                    await run_logger.log("tool_call", {
                        "round": round_idx + 1,
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "success": not has_error,
                        "duration_ms": tool_duration,
                        "item_count": data.get("total", 0) if not has_error else 0,
                    })

                if not has_error:
                    all_tool_results.append({"tool": tc.name, "data": data})

                tool_output = json.dumps(data, ensure_ascii=False, default=str)
                tool_msg = ChatMessage(role="tool", content=tool_output)
                tool_msg.tool_call_id = tc.id  # type: ignore
                tool_messages.append(tool_msg)

                logger.info(
                    f"[agent:{trace_id}] Tool [{tc.name}] "
                    f"{'ERROR' if has_error else 'OK'} "
                    f"duration={tool_duration}ms params={tc.arguments}"
                )

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

        try:
            summary_started = now_iso()
            summary_start = time.perf_counter()
            final_result = await _llm_chat_with_retry(messages, options)
            raw_text = final_result if isinstance(final_result, str) else (final_result.text or "")
            thinking = _extract_thinking(raw_text)
            text = _strip_think_tags(raw_text)
            report_model_call(
                session_id, "生成总结", provider=provider_name,
                model_override=main_options.model, started_at=summary_started,
                duration_ms=round((time.perf_counter() - summary_start) * 1000, 2),
            )
        except Exception as e:
            logger.error(f"[agent:{trace_id}] 最终总结失败: {e}")
            text = "查询完成，但生成总结时出现问题。"
            thinking = ""

        reply = _build_reply(text, all_tool_results, diagnostics, message)
        reply.thinking = thinking if thinking else None
        await _save_conversation(session_id, message, text)
        if run_logger:
            await run_logger.log("done", {
                "intent": "agent",
                "text_length": len(text),
                "tool_count": len(all_tool_results),
                "max_rounds_reached": True,
            })
        return reply

    finally:
        if run_logger:
            try:
                await run_logger.close()
            except Exception as e:
                logger.warning(f"[agent:{trace_id}] 关闭 RunLogger 失败: {e}")
        if session_id:
            CancellationRegistry.cleanup(session_id)


def _build_reply(
    text: str,
    tool_results: List[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    original_message: str,
) -> AssistantReply:
    cards = build_cards_from_tool_results(tool_results)
    return AssistantReply(
        intent="agent",
        text=text,
        cards=cards,
        suggestions=[],
        provider=ai_service.current_provider(),
        diagnostics=diagnostics,
    )


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
