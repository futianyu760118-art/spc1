"""上下文管理 — token 估算与摘要压缩"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_ENCODING = None


def _get_encoding():
    global _ENCODING
    if _ENCODING is None:
        try:
            import tiktoken
            _ENCODING = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"tiktoken 加载失败，回退到字符估算: {e}")
            _ENCODING = False
    return _ENCODING or None


def estimate_tokens(messages: List[Any]) -> int:
    if not messages:
        return 0
    enc = _get_encoding()
    total = 0
    for m in messages:
        content = ""
        if hasattr(m, "content"):
            content = m.content or ""
        elif isinstance(m, dict):
            content = m.get("content", "") or ""
        if enc:
            try:
                total += len(enc.encode(content))
            except Exception:
                total += len(content) // 2
        else:
            total += len(content) // 2
        total += 4
    return total


def estimate_dict_tokens(messages: List[Dict[str, Any]]) -> int:
    if not messages:
        return 0
    enc = _get_encoding()
    total = 0
    for m in messages:
        content = m.get("content", "") or ""
        if enc:
            try:
                total += len(enc.encode(content))
            except Exception:
                total += len(content) // 2
        else:
            total += len(content) // 2
        if m.get("tool_calls"):
            import json
            try:
                total += len(enc.encode(json.dumps(m["tool_calls"], ensure_ascii=False)))
            except Exception:
                total += len(json.dumps(m["tool_calls"], ensure_ascii=False)) // 2
        total += 4
    return total


def should_summarize(
    local_tokens: int,
    api_total_tokens: Optional[int],
    threshold: int,
    enabled: bool,
) -> bool:
    if not enabled:
        return False
    if api_total_tokens and api_total_tokens > threshold:
        return True
    if local_tokens > threshold:
        return True
    return False


def _format_execution(messages: List[Dict[str, Any]]) -> str:
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "assistant":
            text = (content or "").strip()
            lines.append(f"Assistant: {text[:1500]}")
            tcs = m.get("tool_calls") or []
            if tcs:
                names = []
                for tc in tcs:
                    if isinstance(tc, dict):
                        fn = tc.get("function") or {}
                        names.append(fn.get("name", "?"))
                lines.append(f"  → 调用工具: {', '.join(names)}")
        elif role == "tool":
            text = (content or "").strip()
            lines.append(f"  ← 工具结果: {text[:800]}")
    return "\n".join(lines)


async def summarize_round(
    messages: List[Dict[str, Any]],
    round_num: int,
    chat_fn,
) -> str:
    from app.services.ai.base import ChatMessage, ChatOptions

    execution_text = _format_execution(messages)
    if not execution_text:
        return ""

    prompt = f"""请用简洁的中文总结以下 Agent 执行过程（不超过 800 字）：

第 {round_num} 轮：
{execution_text}

要求：
1. 重点说明完成了什么、调用了哪些工具、关键结果
2. 保留关键数据点（订单号、数量、风险等级等）
3. 简洁清晰，不要重复原始 JSON
4. 不要描述用户"""

    try:
        opts = ChatOptions(temperature=0.0, max_tokens=800, timeout=20)
        result = await chat_fn(
            [ChatMessage(role="user", content=prompt)],
            opts,
        )
        if isinstance(result, tuple):
            result = result[0]
        return (result or "").strip()
    except Exception as e:
        logger.warning(f"[context_manager] 摘要 LLM 调用失败: {e}")
        return ""


def build_compressed_messages(
    original: List[Dict[str, Any]],
    system_msg: Dict[str, Any],
    summaries: Dict[int, str],
) -> List[Dict[str, Any]]:
    if not original:
        return [system_msg] if system_msg else []

    new_messages: List[Dict[str, Any]] = []
    if system_msg:
        new_messages.append(system_msg)

    user_indices = [
        i for i, m in enumerate(original) if m.get("role") == "user" and i > 0
    ]
    if not user_indices:
        return [m for m in original if m.get("role") == "system"] + original

    for i, user_idx in enumerate(user_indices):
        new_messages.append(original[user_idx])
        if i in summaries and summaries[i]:
            new_messages.append({
                "role": "user",
                "content": f"[第 {i + 1} 轮执行摘要]\n\n{summaries[i]}",
            })

    return new_messages


def fallback_sliding_window(
    original: List[Dict[str, Any]],
    keep_last: int = 6,
) -> List[Dict[str, Any]]:
    if not original:
        return []
    system_msgs = [m for m in original if m.get("role") == "system"]
    others = [m for m in original if m.get("role") != "system"]
    return system_msgs + others[-keep_last:]


def render_messages_for_summary(messages: List[Any]) -> List[Dict[str, Any]]:
    rendered: List[Dict[str, Any]] = []
    for m in messages:
        if isinstance(m, dict):
            rendered.append(m)
            continue
        d: Dict[str, Any] = {"role": getattr(m, "role", "user"), "content": getattr(m, "content", "") or ""}
        if hasattr(m, "tool_call_id") and m.tool_call_id:
            d["tool_call_id"] = m.tool_call_id
        if hasattr(m, "tool_calls") and m.tool_calls:
            d["tool_calls"] = m.tool_calls
        rendered.append(d)
    return rendered
