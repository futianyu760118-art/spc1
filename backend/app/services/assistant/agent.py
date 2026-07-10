"""单层 Agent — LLM 直接调用 Tools，无中间 Skill/Decider 层"""

import json
import logging
import re
import asyncio
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import ai_service, ChatMessage, ChatOptions, NotSupportedError
from app.services.assistant.tool_registry import get_tool, get_openai_tools_schema
from app.services.assistant.card_builder import build_cards_from_tool_results
from app.services.assistant import session_store
from app.schemas.assistant.schemas import AssistantReply, AssistantCard

logger = logging.getLogger(__name__)

# ─── 配置 ───────────────────────────────────────────────────
MAX_TOOL_ROUNDS = 5       # 最大 Tool 调用轮数
TOOL_EXECUTE_TIMEOUT = 30  # 单个 Tool 执行超时（秒）
MAX_RETRIES = 1            # Tool 执行失败重试次数

# 意图识别提示词
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

# Qwen3 系列模型会输出 <think>...</think> 标签
_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>", re.DOTALL)


def _strip_think_tags(text: str) -> str:
    """去除 Qwen3 模型输出的思考过程标签"""
    if not text:
        return text
    cleaned = _THINK_TAG_RE.sub("", text).strip()
    return cleaned or text


async def _recognize_intent(
    message: str,
    history: List[Dict[str, Any]],
) -> str:
    """识别用户意图
    
    Returns:
        "QUERY_DATA" - 需要查询系统数据
        "ANALYZE_HISTORY" - 仅分析历史数据
        "GENERAL_CHAT" - 一般对话
    """
    try:
        # 构建意图识别消息
        messages = [
            ChatMessage(role="system", content=INTENT_RECOGNITION_PROMPT),
        ]
        
        # 添加最近的对话历史（最多3轮）作为上下文
        recent_history = history[-6:] if len(history) > 6 else history
        for msg in recent_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
        
        # 添加当前消息
        messages.append(ChatMessage(role="user", content=message))
        
        # 调用 LLM 进行意图识别
        options = ChatOptions(temperature=0.0, max_tokens=50, timeout=10)
        result = await ai_service.chat(messages, options)
        
        # 提取意图类型
        intent = result.strip().upper()
        if "QUERY_DATA" in intent:
            return "QUERY_DATA"
        elif "ANALYZE_HISTORY" in intent:
            return "ANALYZE_HISTORY"
        elif "GENERAL_CHAT" in intent:
            return "GENERAL_CHAT"
        else:
            # 默认为查询数据（保守策略）
            logger.warning(f"无法识别意图，返回值: {result}，默认为 QUERY_DATA")
            return "QUERY_DATA"
            
    except Exception as e:
        logger.error(f"意图识别失败: {e}，默认为 QUERY_DATA")
        return "QUERY_DATA"


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
            logger.error(f"{last_error} (attempt {attempt + 1})", exc_info=(attempt == MAX_RETRIES))

        if attempt < MAX_RETRIES:
            await asyncio.sleep(0.5)

    return {"error": last_error}


async def run(
    message: str,
    db: AsyncSession,
    session_id: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    trace_id: str = "",
) -> AssistantReply:
    """运行 Agent：单层 LLM + Tool Calling 循环"""

    diagnostics: Dict[str, Any] = {
        "provider": ai_service.current_provider(),
        "path": "agent",
        "fallback": False,
        "intent": None,
        "llm_rounds": [],
        "tools": [],
        "errors": [],
    }

    # ─── 1. LLM Agent 模式 ───────────────────────────────────
    if ai_service.current_provider() == "rule_based":
        # LLM 不可用，返回提示
        return AssistantReply(
            intent="unknown",
            text="AI 服务暂不可用，请联系管理员配置 AI 服务。",
            suggestions=[],
            provider="rule_based",
        )

    # 加载会话历史
    history = conversation_history or []
    if session_id and not history:
        history = await session_store.get_history(session_id)

    # ─── 2. 意图识别 ───────────────────────────────────────
    intent = await _recognize_intent(message, history)
    diagnostics["intent"] = intent
    logger.info(f"[agent:{trace_id}] 意图识别结果: {intent}")

    # ─── 3. 根据意图决定是否使用工具 ───────────────────────
    # 如果是分析历史或一般对话，不使用工具，直接让 LLM 回答
    if intent in ("ANALYZE_HISTORY", "GENERAL_CHAT"):
        messages: List[Any] = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
        
        # 添加历史消息
        for msg in history[-10:]:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
        
        # 添加当前消息
        messages.append(ChatMessage(role="user", content=message))
        
        try:
            options = ChatOptions(temperature=0.3, max_tokens=4096, timeout=60)
            result = await ai_service.chat(messages, options)
            text = _strip_think_tags(result)
            
            reply = AssistantReply(
                intent=intent.lower(),
                text=text,
                cards=[],
                suggestions=[],
                provider=ai_service.current_provider(),
                diagnostics=diagnostics,
            )
            
            # 保存会话
            await _save_conversation(session_id, message, text)
            return reply
            
        except Exception as e:
            logger.error(f"[agent:{trace_id}] LLM 调用失败: {e}")
            diagnostics["errors"].append({"stage": "llm", "message": str(e)})
            return AssistantReply(
                text="AI 服务调用失败，请稍后重试。",
                suggestions=[],
                provider=ai_service.current_provider(),
            )

    # ─── 4. QUERY_DATA 意图：使用工具查询 ───────────────────
    tools_schema = get_openai_tools_schema()
    if not tools_schema:
        return AssistantReply(text="系统未注册任何工具，请联系管理员。")

    # 构建消息列表
    messages: List[Any] = [ChatMessage(role="system", content=SYSTEM_PROMPT)]

    # 添加历史消息（只保留 user/assistant 文本）
    for msg in history[-10:]:
        role = msg.get("role")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append(ChatMessage(role=role, content=content))

    # 添加当前消息
    messages.append(ChatMessage(role="user", content=message))

    # Tool Calling 循环
    all_tool_results: List[Dict[str, Any]] = []
    options = ChatOptions(temperature=0.1, max_tokens=4096, timeout=120)

    for round_idx in range(MAX_TOOL_ROUNDS):
        round_start = time.perf_counter()

        try:
            result = await ai_service.chat_with_tools(messages, tools_schema, options)
        except Exception as e:
            duration_ms = round((time.perf_counter() - round_start) * 1000, 2)
            diagnostics["llm_rounds"].append({
                "round": round_idx + 1, "status": "error", "duration_ms": duration_ms,
            })
            diagnostics["errors"].append({"stage": "llm", "message": str(e)})
            logger.error(f"[agent:{trace_id}] LLM 调用失败 (round {round_idx + 1}): {e}")
            return AssistantReply(
                text=f"AI 服务调用失败，请稍后重试。",
                suggestions=[],
                provider=ai_service.current_provider(),
            )

        duration_ms = round((time.perf_counter() - round_start) * 1000, 2)
        diagnostics["llm_rounds"].append({
            "round": round_idx + 1,
            "status": "tool_calls" if result.tool_calls else "direct_reply",
            "tool_call_count": len(result.tool_calls),
            "duration_ms": duration_ms,
        })

        # LLM 直接回复（无 tool call）
        if not result.tool_calls:
            text = _strip_think_tags(result.text or "抱歉，我无法理解您的问题。请尝试换一种方式提问。")
            reply = _build_reply(text, all_tool_results, diagnostics, message)
            # 保存会话
            await _save_conversation(session_id, message, text)
            return reply

        # 执行 Tool 调用
        tool_messages = []
        for tc in result.tool_calls:
            tool_start = time.perf_counter()
            data = await _execute_tool(db, tc.name, tc.arguments)
            tool_duration = round((time.perf_counter() - tool_start) * 1000, 2)

            has_error = "error" in data
            diagnostics["tools"].append({
                "name": tc.name,
                "status": "error" if has_error else "success",
                "duration_ms": tool_duration,
            })

            if not has_error:
                all_tool_results.append({"tool": tc.name, "data": data})

            # 构造 tool 结果消息回传给 LLM
            tool_output = json.dumps(data, ensure_ascii=False, default=str)
            tool_msg = ChatMessage(role="tool", content=tool_output)
            tool_msg.tool_call_id = tc.id  # type: ignore
            tool_messages.append(tool_msg)

            logger.info(
                f"[agent:{trace_id}] Tool [{tc.name}] "
                f"{'ERROR' if has_error else 'OK'} "
                f"duration={tool_duration}ms params={tc.arguments}"
            )

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

    # 超过最大轮次，做最终总结
    try:
        final_result = await ai_service.chat(messages, options)
        text = _strip_think_tags(final_result)
    except Exception as e:
        logger.error(f"[agent:{trace_id}] 最终总结失败: {e}")
        text = "查询完成，但生成总结时出现问题。"

    reply = _build_reply(text, all_tool_results, diagnostics, message)
    await _save_conversation(session_id, message, text)
    return reply


def _build_reply(
    text: str,
    tool_results: List[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    original_message: str,
) -> AssistantReply:
    """构建最终回复"""
    # 构建卡片
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
