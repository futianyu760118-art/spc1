"""执行面智能体注册表与 admin 面代理（设计文档 2026-10-20）"""

import asyncio
from dataclasses import dataclass
from uuid import uuid4
from typing import Dict

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.services.ai_config import (
    EXECUTION_ORDER_SCOPE,
    EXECUTION_QUERY_SCOPE,
    EXECUTION_REASONING_SCOPE,
    get_scope_version,
)


@dataclass(frozen=True)
class ExecutionAgentSpec:
    key: str
    label: str
    scope: str
    capability: str
    base_url_setting: str
    supports_recent_reasoning_tasks: bool = False


AGENT_SPECS: Dict[str, ExecutionAgentSpec] = {
    "query": ExecutionAgentSpec(
        key="query",
        label="查询智能体",
        scope=EXECUTION_QUERY_SCOPE,
        capability="query_control_platform",
        base_url_setting="EXECUTION_QUERY_AGENT_BASE_URL",
    ),
    "reasoning": ExecutionAgentSpec(
        key="reasoning",
        label="推理智能体",
        scope=EXECUTION_REASONING_SCOPE,
        capability="reason_control_platform",
        base_url_setting="EXECUTION_REASONING_AGENT_BASE_URL",
        supports_recent_reasoning_tasks=True,
    ),
    "order": ExecutionAgentSpec(
        key="order",
        label="订单智能体",
        scope=EXECUTION_ORDER_SCOPE,
        capability="update_control_platform_order",
        base_url_setting="EXECUTION_ORDER_AGENT_BASE_URL",
    ),
}


def get_agent_spec(agent_key: str) -> ExecutionAgentSpec:
    spec = AGENT_SPECS.get(agent_key)
    if spec is None:
        raise KeyError(agent_key)
    return spec


def _admin_headers() -> dict:
    return {"x-admin-token": get_settings().AGENT_ADMIN_TOKEN}


def _base_url(spec: ExecutionAgentSpec) -> str:
    return (getattr(get_settings(), spec.base_url_setting) or "").rstrip("/")


async def call_agent(base_url: str, path: str, *, timeout: float = 10.0, method: str = "GET") -> dict:
    """代理调用 agent admin 面；不可达返回离线态而非抛错。"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, f"{base_url}{path}", headers=_admin_headers())
        if resp.status_code == 401:
            return {"online": False, "reason": "admin token 不匹配（backend 与 agent 容器的 AGENT_ADMIN_TOKEN 不一致）"}
        if resp.status_code == 503:
            try:
                if resp.json().get("status") == "admin_disabled":
                    return {"online": False, "reason": "agent 未配置 AGENT_ADMIN_TOKEN（admin 面禁用）"}
            except ValueError:
                pass
        resp.raise_for_status()
        try:
            body = resp.json()
        except ValueError:
            return {"online": False, "reason": "响应非 JSON"}
        return {"online": True, **body}
    except httpx.HTTPError as e:
        return {"online": False, "reason": f"agent 不可达: {e.__class__.__name__}"}


async def call_agent_spec(
    spec: ExecutionAgentSpec, path: str, *, timeout: float = 10.0, method: str = "GET"
) -> dict:
    base = _base_url(spec)
    if not base:
        return {"online": False, "reason": f"{spec.base_url_setting} 未配置"}
    return await call_agent(base, path, timeout=timeout, method=method)


async def call_agent_run(
    spec: ExecutionAgentSpec, input: dict, *, timeout: float = 30.0, operator_user_id: str = ""
) -> dict:
    """本地派单：POST /admin/run 同步执行一个 capability（不经 Hub）。

    返回归一化结果，绝不抛错：
    - 离线：{"online": False, "reason": ...}
    - agent 忙：{"online": True, "busy": True, "reason": ...}
    - 成功：{"online": True, "ok": True, "runId": ..., "result": ...}
    - 执行失败：{"online": True, "ok": False, "reason": ...}
    operator_user_id 透传给 agent，供写接口把审计操作人落到真实登录用户。
    """
    base = _base_url(spec)
    if not base:
        return {"online": False, "reason": f"{spec.base_url_setting} 未配置"}
    payload: dict = {"capability": spec.capability, "input": input, "runId": f"local-{uuid4().hex}"}
    if operator_user_id:
        payload["operator"] = {"user_id": str(operator_user_id)}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/admin/run",
                json=payload,
                headers=_admin_headers(),
            )
    except httpx.HTTPError as e:
        return {"online": False, "reason": f"agent 不可达: {e.__class__.__name__}"}
    if resp.status_code == 401:
        return {"online": False, "reason": "admin token 不匹配（backend 与 agent 容器的 AGENT_ADMIN_TOKEN 不一致）"}
    if resp.status_code == 409:
        return {"online": True, "busy": True, "reason": "agent busy（本地或 Hub 派单执行中）"}
    if resp.status_code == 503:
        return {"online": False, "reason": "agent 未配置 AGENT_ADMIN_TOKEN（admin 面禁用）"}
    try:
        body = resp.json()
    except ValueError:
        return {"online": False, "reason": "响应非 JSON"}
    if resp.status_code >= 400:
        reason = body.get("message") or body.get("status") or f"HTTP {resp.status_code}"
        return {"online": True, "ok": False, "reason": str(reason)}
    return {
        "online": True,
        "ok": bool(body.get("ok", True)),
        "runId": body.get("runId"),
        "result": body.get("result"),
    }


def config_pending_restart(status: dict, db_version: int) -> bool:
    if status.get("online") and status.get("configVersion") is not None:
        try:
            return int(status["configVersion"]) != db_version
        except (TypeError, ValueError):
            return False
    return False


async def fetch_recent_reasoning_tasks(db) -> list:
    rows = (await db.execute(text(
        "SELECT task_id, task_type, status, llm_called, error_code, duration_ms, created_at "
        "FROM reasoning_task ORDER BY id DESC LIMIT 10"
    ))).mappings().all()
    return [dict(r) for r in rows]


def summarize_agent_status(spec: ExecutionAgentSpec, status: dict, db_version: int) -> dict:
    return {
        "key": spec.key,
        "label": spec.label,
        "scope": spec.scope,
        "capability": spec.capability,
        "online": bool(status.get("online")),
        "registered": status.get("registered"),
        "agentId": status.get("agentId"),
        "configVersion": status.get("configVersion"),
        "currentRunId": status.get("currentRunId"),
        "uptimeS": status.get("uptimeS"),
        "capabilities": status.get("capabilities", []),
        "reason": status.get("reason"),
        "db_version": db_version,
        "config_pending_restart": config_pending_restart(status, db_version),
    }


async def list_agent_statuses(db) -> list:
    versions = {spec.key: await get_scope_version(db, spec.scope) for spec in AGENT_SPECS.values()}
    results = await asyncio.gather(
        *(call_agent_spec(spec, "/admin/status", timeout=3.0) for spec in AGENT_SPECS.values())
    )
    return [
        summarize_agent_status(spec, status, versions[spec.key])
        for spec, status in zip(AGENT_SPECS.values(), results)
    ]
