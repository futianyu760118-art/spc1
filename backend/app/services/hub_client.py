"""AEOS Hub 能力调用客户端 —— 中台调用其它系统只读能力的统一入口。

契约：所有 Hub HTTP 经 SPC 单一网关（gateway_client），backend 不再直连 Hub。
- POST /internal/hub/borrow-orders          发起能力调用（202 + 借调单，requestId 幂等）
- GET  /internal/hub/borrow-orders/{id}     轮询借调结果
- GET  /internal/hub/capability-invocations 能力模板目录
- 错误码映射见 _ERROR_MESSAGES（执行单 §8）；所有函数绝不抛错。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.services import gateway_client

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_S = 2.0
DEFAULT_POLL_BUDGET_S = 30.0
CATALOG_TTL_S = 300.0
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "recalled"}

# 执行单 §8 错误码 → 用户可读原因（消息同时透传原始 code 供排查）
_ERROR_MESSAGES = {
    "INVALID_ARGUMENT": "参数缺失或类型错误",
    "PAYLOAD_TOO_LARGE": "请求参数过大",
    "AUTH_REQUIRED": "Hub 系统鉴权失败",
    "SELF_BORROW_FORBIDDEN": "不能通过 Hub 调用本系统能力",
    "SELF_INVOCATION_FORBIDDEN": "不能通过 Hub 调用本系统能力",
    "CAPABILITY_NOT_FOUND": "Hub 能力模板不存在",
    "ORDER_NOT_FOUND": "借调单不存在或无权查看",
    "REQUEST_CONFLICT": "requestId 与已有调用冲突",
    "TARGET_NOT_ELIGIBLE": "目标系统暂不可用",
    "VERSION_MISMATCH": "能力模板版本不兼容",
    "TOO_MANY_OPEN_ORDERS": "在途借调单过多，请稍后重试",
    "DISPATCH_FAILED": "Hub 派单失败，请稍后重试",
    "NOT_CONFIGURED": "Hub 能力调用面未配置",
}

# 能力目录缓存（TTL 300s）：助手工具枚举与执行期校验共用
_catalog_cache: Dict[str, Any] = {"templates": None, "fetched_at": 0.0}

DEFAULT_TOOL_CAPABILITIES = ["query_plm"]


def is_hub_enabled() -> bool:
    return gateway_client.is_gateway_enabled()


def _new_request_id(trace_id: str = "") -> str:
    token = (trace_id or uuid4().hex)[:48]
    return f"spc-{token}-{uuid4().hex[:8]}"


def capability_names() -> List[str]:
    """助手工具枚举用（同步读缓存）：排除本系统能力；缓存为空兜底 query_plm。"""
    templates = _catalog_cache.get("templates") or []
    names = [
        t.get("capability")
        for t in templates
        if t.get("providerSystem") != "control-platform" and t.get("capability")
    ]
    return names or list(DEFAULT_TOOL_CAPABILITIES)


def provider_system(capability: str) -> Optional[str]:
    templates = _catalog_cache.get("templates") or []
    matched = next((t for t in templates if t.get("capability") == capability), None)
    return (matched or {}).get("providerSystem")


def _parse_error_code(body: Optional[Dict[str, Any]]) -> Optional[str]:
    if isinstance(body, dict):
        return body.get("code") or (body.get("error") or {}).get("code")
    return None


def _readable_error(code: Optional[str], fallback: str) -> str:
    if not code:
        return fallback
    detail = _ERROR_MESSAGES.get(code)
    return f"{detail}（Hub 错误码 {code}）" if detail else f"Hub 返回错误（{code}）"


async def list_templates() -> List[Dict[str, Any]]:
    """拉取能力目录；失败返回空列表并告警（降级，不抛错）。"""
    result = await gateway_client.list_templates()
    if not result.get("ok"):
        logger.warning(f"[hub_client] 拉取能力目录失败: {result.get('error') or result.get('text')}")
        return []
    body = result.get("body") or {}
    if not isinstance(body, dict):
        logger.warning("[hub_client] 能力目录响应格式非法")
        return []
    return body.get("templates") or []


async def refresh_catalog(force: bool = False) -> List[Dict[str, Any]]:
    """按 TTL 刷新目录缓存（force=True 立即刷新），返回当前缓存内容。"""
    if not force and _catalog_cache["templates"] is not None:
        if time.monotonic() - _catalog_cache["fetched_at"] < CATALOG_TTL_S:
            return _catalog_cache["templates"]
    templates = await list_templates()
    if templates:
        _catalog_cache["templates"] = templates
        _catalog_cache["fetched_at"] = time.monotonic()
    return _catalog_cache["templates"] or []


async def validate_capability(capability: str) -> Optional[str]:
    """校验能力在目录内且非本系统；返回错误原因（None=合法）。"""
    await refresh_catalog()
    templates = _catalog_cache["templates"] or []
    if not templates:
        return "Hub 能力目录不可用，请稍后重试"
    matched = next((t for t in templates if t.get("capability") == capability), None)
    if matched is None:
        return f"能力 {capability} 不在 Hub 能力目录白名单内"
    if matched.get("providerSystem") == "control-platform":
        return "不能通过 Hub 调用本系统能力"
    return None


async def invoke_capability(
    capability: str,
    input_data: Dict[str, Any],
    *,
    to_system: str = "",
    caller: Optional[Dict[str, Any]] = None,
    trace_id: str = "",
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """发起能力调用；返回 {"ok", "invocation", "order", "request_id", "error"}，绝不抛错。"""
    if not is_hub_enabled():
        return {"ok": False, "invocation": None, "order": None, "request_id": "",
                "error": "网关未配置，跨系统查询暂不可用"}
    if not to_system:
        return {"ok": False, "invocation": None, "order": None, "request_id": "",
                "error": "Hub 能力目录缺少 providerSystem"}
    request_id = request_id or _new_request_id(trace_id)
    payload: Dict[str, Any] = {
        "requestId": request_id,
        "capability": capability,
        "toSystem": to_system,
        "input": input_data or {},
    }
    if caller:
        payload["caller"] = caller
    result = await gateway_client.post_borrow_order(payload)
    if not result.get("ok"):
        code = _parse_error_code(result.get("body"))
        return {"ok": False, "invocation": None, "order": None, "request_id": request_id,
                "error": _readable_error(code, result.get("error") or "Hub 拒绝调用")}
    body = result.get("body") or {}
    if not isinstance(body, dict):
        return {"ok": False, "invocation": None, "order": None, "request_id": request_id,
                "error": "Hub 响应格式非法"}
    return {"ok": True, "invocation": body.get("invocation") or {}, "order": body.get("order") or {},
            "request_id": request_id, "error": None}


async def get_borrow_order(borrow_order_id: str) -> Dict[str, Any]:
    """查询借调单；返回 {"ok", "order", "error"}。"""
    result = await gateway_client.get_borrow_order(borrow_order_id)
    if not result.get("ok"):
        code = _parse_error_code(result.get("body"))
        return {"ok": False, "order": None,
                "error": _readable_error(code, result.get("error") or "查询借调单失败")}
    body = result.get("body") or {}
    if not isinstance(body, dict):
        return {"ok": False, "order": None, "error": "Hub 响应格式非法"}
    return {"ok": True, "order": body.get("order") or {}, "error": None}


async def query_and_poll(
    capability: str,
    input_data: Dict[str, Any],
    *,
    to_system: str = "",
    caller: Optional[Dict[str, Any]] = None,
    trace_id: str = "",
    budget_s: float = DEFAULT_POLL_BUDGET_S,
    interval_s: float = DEFAULT_POLL_INTERVAL_S,
) -> Dict[str, Any]:
    """发起能力调用并轮询至终态（30s 收口）。

    返回 {"ok", "status", "result", "error", "borrow_order_id", "request_id"}；
    超时未终态 ok=False + 提示"处理中"（附 borrow_order_id 供后续追查）。
    """
    invoked = await invoke_capability(
        capability, input_data, to_system=to_system, caller=caller, trace_id=trace_id,
    )
    if not invoked.get("ok"):
        return {"ok": False, "status": None, "result": None, "error": invoked.get("error"),
                "borrow_order_id": (invoked.get("invocation") or {}).get("borrowOrderId"),
                "request_id": invoked.get("request_id")}
    order_id = ((invoked.get("invocation") or {}).get("borrowOrderId")
                or (invoked.get("order") or {}).get("orderId"))
    if not order_id:
        return {"ok": False, "status": "dispatched", "result": None, "error": "Hub 未返回借调单号",
                "borrow_order_id": None, "request_id": invoked.get("request_id")}
    deadline = time.monotonic() + budget_s
    while True:
        polled = await get_borrow_order(order_id)
        if not polled.get("ok"):
            return {"ok": False, "status": None, "result": None, "error": polled.get("error"),
                    "borrow_order_id": order_id, "request_id": invoked.get("request_id")}
        order = polled["order"]
        status = order.get("status")
        if status in TERMINAL_STATUSES:
            if status == "completed":
                return {"ok": True, "status": status, "result": order.get("result"), "error": None,
                        "borrow_order_id": order_id, "request_id": invoked.get("request_id")}
            return {"ok": False, "status": status, "result": None,
                    "error": f"借调单已终止（{status}）", "borrow_order_id": order_id,
                    "request_id": invoked.get("request_id")}
        if time.monotonic() >= deadline:
            return {"ok": False, "status": status, "result": None,
                    "error": f"查询仍在处理中（借调单 {order_id}），请稍后重试",
                    "borrow_order_id": order_id, "request_id": invoked.get("request_id")}
        await asyncio.sleep(interval_s)
