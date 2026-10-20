"""AEOS Hub 助手观测上报（assistant-events）——只发元数据+摘要，失败仅记日志不影响主流程。

契约：《中台助手调用留痕-接入清单》POST {AEOS_HUB_BASE}/api/system/assistant-events
- traceId 用中台会话 ID（一次对话串成一个 trace，Hub 按 traceId 归并会话）
- 鉴权头 x-aeos-system-id（非 ASCII 必须 URL 编码）/ x-aeos-system-token（HMAC）
- AEOS_HUB_BASE / AEOS_SYSTEM_ID / AEOS_SYSTEM_TOKEN 三项任一缺失即整体停用
- 不等待回执：fire-and-forget，上报失败/被拒只写日志
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote
from uuid import uuid4

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 3.0

_client: Optional[httpx.AsyncClient] = None


def is_enabled() -> bool:
    settings = get_settings()
    return bool(settings.AEOS_HUB_BASE and settings.AEOS_SYSTEM_ID and settings.AEOS_SYSTEM_TOKEN)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        settings = get_settings()
        # Hub 用私有 CA 签发时只让上报客户端信任该 CA，避免影响其它 HTTPS 出站（OpenAI/企微等）
        ca_cert = settings.AEOS_HUB_CA_CERT or os.environ.get("REQUESTS_CA_BUNDLE", "")
        _client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, verify=ca_cert or True)
    return _client


def _model_id(provider: str, model_override: Optional[str]) -> str:
    if model_override:
        return model_override
    settings = get_settings()
    if provider == "openai":
        return settings.AI_OPENAI_MODEL
    if provider == "dashscope":
        return settings.AI_DASHSCOPE_MODEL
    return provider or ""


def build_usage(
    provider: str,
    model_override: Optional[str],
    token_usage: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """TokenUsage → Hub usage 字段；无 usage 时只带 modelId（用量台账需 tokensIn/tokensOut>0 才记账）"""
    model_id = _model_id(provider, model_override)
    if not model_id:
        return None
    if token_usage is None:
        return {"modelId": model_id}
    return {
        "modelId": model_id,
        "tokensIn": int(token_usage.prompt_tokens or 0),
        "cachedTokens": int(token_usage.cached_tokens or 0),
        "tokensOut": int(token_usage.completion_tokens or 0),
    }


async def _post(payload: Dict[str, Any]) -> None:
    settings = get_settings()
    headers = {
        "x-aeos-system-id": quote(settings.AEOS_SYSTEM_ID, safe=""),
        "x-aeos-system-token": settings.AEOS_SYSTEM_TOKEN,
    }
    try:
        resp = await _get_client().post(
            f"{settings.AEOS_HUB_BASE.rstrip('/')}/api/system/assistant-events",
            json=payload,
            headers=headers,
        )
    except Exception as exc:
        logger.warning(
            f"[hub_reporter] 上报失败 trace={payload.get('traceId')} event={payload.get('event')}: {exc}"
        )
        return
    if resp.status_code >= 400:
        logger.warning(
            f"[hub_reporter] Hub 拒绝 trace={payload.get('traceId')} event={payload.get('event')} "
            f"status={resp.status_code} body={resp.text[:200]}"
        )
        return
    try:
        body = resp.json()
        if not body.get("accepted", True):
            logger.warning(f"[hub_reporter] Hub 未接收 eventId={payload.get('eventId')}: {body}")
    except Exception:
        pass


def report_assistant_event(
    trace_id: str,
    event: str,
    name: str,
    status: str = "info",
    summary: str = "",
    detail: Optional[Dict[str, Any]] = None,
    usage: Optional[Dict[str, Any]] = None,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """fire-and-forget 上报一条助手观测事件；未配置或 trace 为空时直接跳过，绝不抛异常。"""
    if not trace_id or not is_enabled():
        return
    payload = {
        "eventId": f"{trace_id}-{event}-{uuid4().hex[:8]}",
        "traceId": trace_id,
        "event": event,
        "name": name[:100],
        "status": status,
        "summary": (summary or "")[:500],
        "detail": detail,
        "usage": usage,
        "startedAt": started_at,
        "endedAt": ended_at,
        "durationMs": round(duration_ms, 2) if duration_ms is not None else None,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    try:
        asyncio.create_task(_post(payload))
    except RuntimeError as exc:
        logger.warning(f"[hub_reporter] 无法创建上报任务: {exc}")


def report_model_call(
    trace_id: str,
    name: str,
    *,
    provider: str,
    model_override: Optional[str] = None,
    token_usage: Optional[Any] = None,
    started_at: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """上报一次大模型调用；rule_based（未接真实模型）不报。"""
    if not trace_id or provider == "rule_based":
        return
    report_assistant_event(
        trace_id=trace_id,
        event="model_call",
        name=name,
        status="completed",
        summary=f"模型调用：{name}",
        usage=build_usage(provider, model_override, token_usage),
        started_at=started_at,
        ended_at=now_iso() if started_at else None,
        duration_ms=duration_ms,
    )
