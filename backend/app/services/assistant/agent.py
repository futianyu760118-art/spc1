"""智能助手 — 意图识别 + 转发给本地编排器（AI 自主 ReAct）。

助手保持薄：不持有本地 DB 工具。闲聊 / 分析历史直接回复；任务类请求交给
orchestrator.run_reaction，由 AI 逐步决定调用 query / reasoning / order 三个执行面智能体。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent.context import UserContext
from app.services.agent.prompt import build_agent_system_prompt
from app.services.ai import ai_service, ChatMessage, ChatOptions
from app.services.ai_config import (
    ASSISTANT_CONFIG_DEFS,
    ASSISTANT_SCOPE,
    get_scope_config,
)
from app.services.assistant import session_store
from app.services.assistant.cancellation import CancellationRegistry
from app.services.assistant.hub_reporter import now_iso, report_model_call
from app.services.assistant.orchestrator import (
    LLM_RETRY_CONFIG,
    _extract_thinking,
    _strip_think_tags,
    maybe_summarize,
    resolve_system_prompt,
    run_reaction,
)
from app.services.assistant.retry import async_retry
from app.services.assistant.run_logger import RunLogger
from app.schemas.assistant.schemas import (
    AssistantCard,
    AssistantReply,
    OrchestrationStep,
    WriteConfirmationInfo,
)

logger = logging.getLogger(__name__)

INTENT_RECOGNITION_PROMPT = """你是一个意图识别助手。分析用户的消息，判断用户的意图类型。

意图类型：
1. QUERY_DATA - 需要查询系统数据 / 分析业务问题 / 修改订单数据（交给智能体编排器）
   示例：
   - "查询订单HJ202604-0018-0086的信息"
   - "有哪些逾期的订单？"
   - "显示所有高风险订单"
   - "订单HJ202604-0018-0086齐套了吗？"
    - "分析这个订单的交期风险"
    - "把订单HJ202604-0018-0086的出货计划改到2026-11-01"
    - "查一下这个产品的BOM明细"
    - "帮我提个反馈：优化系统界面"
    - "撤销刚才的反馈"

2. ANALYZE_HISTORY - 仅分析聊天历史中已有的数据（不需要调用智能体）
   示例：
   - "帮我分析一下这些订单的风险分布"
   - "总结一下上面的数据"
   - "这些订单有什么共同特点？"

3. GENERAL_CHAT - 一般对话（不需要调用智能体）
   示例：
   - "你好"
   - "谢谢"
   - "你能做什么？"

判断规则：
- 如果用户明确提到要"查询"、"搜索"、"显示"、"找"某个具体的订单号、供应商、物料等，判断为 QUERY_DATA
- 如果用户要求"分析"、"评估"某业务对象的风险/交期/齐套/品质/生产，判断为 QUERY_DATA
- 如果用户要求修改订单数据（出货计划、发货完成、验货、上线时间），判断为 QUERY_DATA
- 如果用户要求提交问题反馈/建议/咨询，或撤销反馈，判断为 QUERY_DATA
- 如果用户使用"这些"、"上面"、"刚才"等指代词，且要求对已有数据做分析、总结、对比，判断为 ANALYZE_HISTORY
- 其他情况判断为 GENERAL_CHAT

请只返回意图类型（QUERY_DATA、ANALYZE_HISTORY 或 GENERAL_CHAT），不要有其他内容。"""


async def _load_runtime_config(db: AsyncSession) -> Dict[str, Any]:
    """每次请求读 DB 配置（无缓存，多实例强一致）；读失败回退默认值不阻断对话"""
    try:
        return await get_scope_config(db, ASSISTANT_SCOPE)
    except Exception as e:
        logger.warning(f"[agent] 读取运行时配置失败，使用默认值: {e}")
        return {k: d.default for k, d in ASSISTANT_CONFIG_DEFS.items()}


@async_retry(LLM_RETRY_CONFIG)
async def _intent_chat_with_retry(messages: List[ChatMessage], options: ChatOptions) -> str:
    return await ai_service.chat(messages, options)


@async_retry(LLM_RETRY_CONFIG)
async def _llm_chat_with_retry(messages: List[ChatMessage], options: ChatOptions) -> str:
    return await ai_service.chat(messages, options)


async def _recognize_intent(
    message: str,
    history: List[Dict[str, Any]],
    intent_prompt: Optional[str] = None,
    model_override: Optional[str] = None,
) -> str:
    try:
        intent_system = intent_prompt or INTENT_RECOGNITION_PROMPT
        messages = [ChatMessage(role="system", content=intent_system)]
        recent_history = history[-6:] if len(history) > 6 else history
        for msg in recent_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
        messages.append(ChatMessage(role="user", content=message))

        # 推理模型会先消耗 reasoning token；预算过小会导致 content 为空、意图恒为兜底值
        options = ChatOptions(temperature=0.0, max_tokens=2048, model=model_override, timeout=30)
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


async def run(
    message: str,
    db: AsyncSession,
    session_id: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    trace_id: str = "",
    user_id: str = "",
    user_context: Optional[UserContext] = None,
    conversation_id: Optional[int] = None,
) -> AssistantReply:
    """运行助手：意图识别 → 闲聊直答 / 任务交本地编排器（ReAct）"""

    provider_name = ai_service.current_provider()

    rt = await _load_runtime_config(db)
    disabled = set(rt.get("disabled_tools") or [])
    system_prompt = resolve_system_prompt(rt.get("system_prompt"), disabled)
    if user_context is not None:
        system_prompt = build_agent_system_prompt(system_prompt, user_context)
    intent_prompt = (rt.get("intent_prompt") or "").strip() or None
    model_override = (rt.get("model_name") or "").strip() or None

    diagnostics: Dict[str, Any] = {
        "provider": provider_name,
        "path": "agent",
        "intent": None,
        "llm_rounds": [],
        "tools": [],
        "errors": [],
    }

    run_logger: Optional[RunLogger] = None
    if trace_id:
        try:
            run_logger = RunLogger(trace_id=trace_id, session_id=session_id, user_id=user_id)
        except Exception as e:
            logger.warning(f"[agent:{trace_id}] 初始化 RunLogger 失败: {e}")

    if session_id:
        await CancellationRegistry.get_or_create(session_id)

    try:
        if run_logger:
            await run_logger.log("request", {"message": message[:500], "provider": provider_name})

        if provider_name == "rule_based":
            if run_logger:
                await run_logger.log("error", {"stage": "init", "message": "AI provider unavailable"})
            return AssistantReply(
                intent="unknown",
                text="AI 服务暂不可用，请联系管理员配置 AI 服务。",
                suggestions=[],
                provider="rule_based",
                conversation_id=conversation_id,
            )

        if _check_cancelled(session_id, run_logger):
            return AssistantReply(text="对话已取消。", provider=provider_name, conversation_id=conversation_id)

        history = conversation_history or []
        if session_id and not history:
            history = await session_store.get_history(session_id)

        if run_logger:
            await run_logger.log("intent_start", {"message_preview": message[:200]})

        intent_started = now_iso()
        intent_start = time.perf_counter()
        intent = await _recognize_intent(message, history, intent_prompt, model_override)
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
            messages: List[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
            for msg in history[-10:]:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append(ChatMessage(role=role, content=content))
            messages.append(ChatMessage(role="user", content=message))
            messages = await maybe_summarize(messages, run_logger, session_id)

            options = ChatOptions(
                temperature=rt.get("temperature", 0.1),
                max_tokens=rt.get("max_tokens", 4096),
                model=model_override,
                timeout=60,
            )
            chat_started = now_iso()
            chat_start = time.perf_counter()
            try:
                result = await _llm_chat_with_retry(messages, options)
            except Exception as e:
                logger.error(f"[agent:{trace_id}] LLM 调用失败: {e}")
                diagnostics["errors"].append({"stage": "llm", "message": str(e)})
                if run_logger:
                    await run_logger.log("error", {"stage": "llm", "message": str(e)})
                return AssistantReply(
                    text="AI 服务调用失败，请稍后重试。", suggestions=[], provider=provider_name,
                    conversation_id=conversation_id,
                )
            report_model_call(
                session_id, "生成回复", provider=provider_name, model_override=model_override,
                started_at=chat_started,
                duration_ms=round((time.perf_counter() - chat_start) * 1000, 2),
            )
            raw_text = result if isinstance(result, str) else (result.text or "")
            thinking = _extract_thinking(raw_text)
            text = _strip_think_tags(raw_text)

            if run_logger:
                await run_logger.log("llm_response", {
                    "intent": intent, "text_length": len(text), "thinking_length": len(thinking),
                })

            await _save_conversation(session_id, message, text)
            return AssistantReply(
                intent=intent.lower(),
                text=text,
                thinking=thinking if thinking else None,
                cards=[],
                suggestions=[],
                provider=provider_name,
                conversation_id=conversation_id,
                diagnostics=diagnostics,
            )

        # 任务 → 本地编排器（AI 自主 ReAct）
        text = ""
        cards: List[AssistantCard] = []
        steps: List[OrchestrationStep] = []
        confirmation: Optional[WriteConfirmationInfo] = None
        error_message: Optional[str] = None
        cancelled_reason: Optional[str] = None

        async for event, data in run_reaction(
            message, history,
            system_prompt=system_prompt, model_override=model_override,
            temperature=rt.get("temperature", 0.1), max_tokens=rt.get("max_tokens", 4096),
            max_tool_rounds=rt.get("max_tool_rounds", 6), max_agent_calls=rt.get("max_agent_calls", 8),
            disabled_tools=disabled, session_id=session_id, trace_id=trace_id, user_id=user_id,
            run_logger=run_logger, provider_name=provider_name,
            stream_final=False,
            db=db, user_context=user_context,
        ):
            if event == "delta":
                text += data.get("text") or ""
            elif event == "cards":
                cards = [AssistantCard(**c) for c in data.get("cards") or []]
            elif event == "done":
                if not text and data.get("text"):
                    text = data["text"]
                steps = [OrchestrationStep(**s) for s in data.get("steps") or []]
                if data.get("confirmation"):
                    confirmation = WriteConfirmationInfo(**data["confirmation"])
                diag = data.get("diagnostics") or {}
                diagnostics["llm_rounds"] = diag.get("llm_rounds") or []
                diagnostics["tools"] = diag.get("tools") or []
                diagnostics["errors"] = diag.get("errors") or []
                diagnostics["total_tokens"] = diag.get("total_tokens")
                if data.get("partial") and data.get("partial_reason"):
                    diagnostics["errors"].append({
                        "stage": "orchestrator", "message": data["partial_reason"],
                    })
            elif event == "confirmation_required":
                confirmation = WriteConfirmationInfo(**data)
            elif event == "cancelled":
                cancelled_reason = data.get("reason")
            elif event == "error":
                error_message = data.get("message")

        if cancelled_reason:
            return AssistantReply(text="对话已取消。", provider=provider_name, diagnostics=diagnostics, conversation_id=conversation_id)

        if confirmation:
            text = text or "检测到订单写操作，已生成确认单：请核对「旧值 → 新值」后确认执行或取消。"
        elif error_message and not text:
            text = error_message
        elif not text:
            text = "抱歉，我无法理解您的问题。请尝试换一种方式提问。"

        await _save_conversation(session_id, message, text)
        if run_logger:
            await run_logger.log("done", {
                "intent": "agent",
                "text_length": len(text),
                "step_count": len(steps),
                "has_confirmation": bool(confirmation),
            })

        return AssistantReply(
            intent="agent",
            text=text,
            cards=cards,
            steps=steps,
            confirmation=confirmation,
            suggestions=[],
            provider=provider_name,
            conversation_id=conversation_id,
            diagnostics=diagnostics,
        )

    finally:
        if run_logger:
            try:
                await run_logger.close()
            except Exception as e:
                logger.warning(f"[agent:{trace_id}] 关闭 RunLogger 失败: {e}")
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
