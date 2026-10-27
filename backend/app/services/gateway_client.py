"""backend -> SPC 网关内网 HTTP 客户端（所有 Hub HTTP 的唯一出口）。"""

import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BORROW_ORDERS_PATH = "/internal/hub/borrow-orders"
CATALOG_PATH = "/internal/hub/capability-invocations"
ASSISTANT_EVENTS_PATH = "/internal/hub/assistant-events"


def is_gateway_enabled() -> bool:
    settings = get_settings()
    return bool(settings.GATEWAY_BASE_URL and settings.GATEWAY_INTERNAL_TOKEN)


def _headers() -> Dict[str, str]:
    return {"X-Gateway-Token": get_settings().GATEWAY_INTERNAL_TOKEN}


def _base_url() -> str:
    return get_settings().GATEWAY_BASE_URL.rstrip("/")


async def request(
    method: str,
    path: str,
    *,
    json: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    if not is_gateway_enabled():
        return {"ok": False, "status": 0, "body": None, "text": "",
                "error": "网关未配置（GATEWAY_BASE_URL / GATEWAY_INTERNAL_TOKEN）"}
    try:
        async with httpx.AsyncClient(timeout=timeout or get_settings().GATEWAY_HUB_TIMEOUT_S) as client:
            resp = await client.request(method, f"{_base_url()}{path}", json=json, headers=_headers())
    except Exception as exc:
        logger.warning(f"[gateway_client] {method} {path} 失败: {exc}")
        return {"ok": False, "status": 0, "body": None, "text": "", "error": f"网关连接失败：{exc}"}
    try:
        body = resp.json()
    except Exception:
        body = None
    return {
        "ok": resp.status_code < 400,
        "status": resp.status_code,
        "body": body,
        "text": resp.text[:1000],
        "error": None if resp.status_code < 400 else f"网关返回 HTTP {resp.status_code}",
    }


async def post_borrow_order(payload: Dict[str, Any]) -> Dict[str, Any]:
    return await request("POST", BORROW_ORDERS_PATH, json=payload)


async def get_borrow_order(order_id: str) -> Dict[str, Any]:
    return await request("GET", f"{BORROW_ORDERS_PATH}/{quote(order_id, safe='')}")


async def list_templates() -> Dict[str, Any]:
    return await request("GET", CATALOG_PATH)


async def post_assistant_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    # 观测上报是 fire-and-forget，用短超时避免慢 Hub 堆积任务
    return await request("POST", ASSISTANT_EVENTS_PATH, json=payload, timeout=5.0)
