"""网关派单解析：caller -> 用户 Agent，能力校验，审计，actor token。"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent.agent import Agent
from app.models.agent.gateway import GatewayDispatchLog
from app.models.basicdata.user import SysUser
from app.services.agent.actor import issue_actor_token
from app.services.agent.capabilities import allowed_query_paths, allowed_reasoning_types
from app.services.agent.context import load_agent_context

USER_COLUMNS = {
    "emp_code": SysUser.emp_code,
    "scm_employee_id": SysUser.scm_employee_id,
    "wecom_user_id": SysUser.wecom_user_id,
    "id": SysUser.id,
}


@dataclass
class DispatchResolution:
    ok: bool
    mode: str
    agent: Optional[Agent] = None
    user: Optional[SysUser] = None
    actor_token: Optional[str] = None
    reject_reason: Optional[str] = None
    caller_user_mismatch: bool = False


def _value(caller: Dict[str, Any], key: str) -> Optional[str]:
    raw = (caller or {}).get(key)
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


async def _user_by_external_id(db: AsyncSession, value: str) -> Optional[SysUser]:
    field = (get_settings().GATEWAY_CALLER_USER_ID_FIELD or "emp_code").strip()
    column = USER_COLUMNS.get(field)
    if column is None:
        return None
    if field in ("id", "scm_employee_id"):
        try:
            return (await db.execute(select(SysUser).where(column == int(value)))).scalars().first()
        except (TypeError, ValueError):
            return None
    return (await db.execute(select(SysUser).where(column == str(value)))).scalars().first()


async def _resolve_agent(
    db: AsyncSession, caller: Dict[str, Any]
) -> Tuple[Optional[Agent], Optional[SysUser], bool, Optional[str]]:
    agent_no = _value(caller, "agentId")
    external_user_id = _value(caller, "userId")

    if agent_no:
        agent = (await db.execute(select(Agent).where(Agent.agent_no == agent_no))).scalars().first()
        if not agent:
            return None, None, False, "AGENT_NOT_FOUND"
        user = await db.get(SysUser, int(agent.user_id))
        if not user or not user.is_active:
            return agent, user, False, "USER_DISABLED"
        if agent.status != "active":
            return agent, user, False, "AGENT_DISABLED"
        mismatch = False
        if external_user_id:
            other = await _user_by_external_id(db, external_user_id)
            mismatch = bool(other and int(other.id) != int(user.id))
        return agent, user, mismatch, None

    if external_user_id:
        user = await _user_by_external_id(db, external_user_id)
        if not user:
            return None, None, False, "USER_NOT_FOUND"
        if not user.is_active:
            return None, user, False, "USER_DISABLED"
        agent = (await db.execute(select(Agent).where(Agent.user_id == user.id))).scalars().first()
        if not agent:
            return None, user, False, "AGENT_NOT_FOUND"
        if agent.status != "active":
            return agent, user, False, "AGENT_DISABLED"
        return agent, user, False, None

    return None, None, False, None


def _capability_reject(ctx, capability: str, input_data: Dict[str, Any]) -> Optional[str]:
    effective = ctx.effective_capabilities
    if capability == "query_control_platform":
        if not any(code.startswith("query.") for code in effective):
            return "CAPABILITY_DENIED"
        path = (input_data or {}).get("path")
        if path and path not in allowed_query_paths(effective):
            return "CAPABILITY_DENIED"
        return None
    if capability == "reason_control_platform":
        if not any(code.startswith("reason.") for code in effective):
            return "CAPABILITY_DENIED"
        task_type = (input_data or {}).get("task_type")
        if task_type and task_type not in allowed_reasoning_types(effective):
            return "CAPABILITY_DENIED"
        return None
    return "INVALID_ARGUMENT"


@dataclass
class AuditContext:
    run_id: str
    trace_id: Optional[str]
    capability: str
    caller: Dict[str, Any]


def _audit(db: AsyncSession, ctx: AuditContext, resolution: DispatchResolution) -> None:
    db.add(GatewayDispatchLog(
        run_id=ctx.run_id,
        trace_id=ctx.trace_id,
        capability=ctx.capability,
        caller_system_id=_value(ctx.caller, "systemId"),
        caller_agent_id=_value(ctx.caller, "agentId"),
        caller_user_id=_value(ctx.caller, "userId"),
        caller_task_id=_value(ctx.caller, "taskId"),
        caller_trace_id=_value(ctx.caller, "traceId"),
        resolved_agent_id=int(resolution.agent.id) if resolution.agent else None,
        resolved_agent_no=resolution.agent.agent_no if resolution.agent else None,
        resolved_user_id=int(resolution.user.id) if resolution.user else None,
        mode=resolution.mode,
        result="routed" if resolution.ok else "rejected",
        reject_reason=resolution.reject_reason,
        caller_user_mismatch=resolution.caller_user_mismatch,
    ))


async def resolve_dispatch(
    db: AsyncSession,
    *,
    run_id: str,
    trace_id: Optional[str],
    capability: str,
    input_data: Dict[str, Any],
    caller: Optional[Dict[str, Any]],
) -> DispatchResolution:
    caller = caller or {}
    audit_ctx = AuditContext(
        run_id=run_id, trace_id=trace_id, capability=capability, caller=caller,
    )
    agent, user, mismatch, reason = await _resolve_agent(db, caller)
    is_system = not _value(caller, "agentId") and not _value(caller, "userId")
    agent_ctx = None

    resolution: DispatchResolution
    if reason:
        resolution = DispatchResolution(
            ok=False, mode="user", agent=agent, user=user,
            reject_reason=reason, caller_user_mismatch=mismatch,
        )
    elif is_system:
        resolution = DispatchResolution(ok=True, mode="system")
    else:
        agent_ctx = await load_agent_context(db, user)
        reason = _capability_reject(agent_ctx, capability, input_data)
        if reason:
            resolution = DispatchResolution(
                ok=False, mode="user", agent=agent, user=user,
                reject_reason=reason, caller_user_mismatch=mismatch,
            )
        else:
            resolution = DispatchResolution(
                ok=True, mode="user", agent=agent, user=user,
                caller_user_mismatch=mismatch,
            )

    _audit(db, audit_ctx, resolution)
    await db.flush()
    if resolution.ok and resolution.mode == "user":
        resolution.actor_token = issue_actor_token(
            user_id=int(user.id),
            agent_id=int(agent.id),
            username=user.username or "",
            role=agent_ctx.role_code,
        )
    return resolution
