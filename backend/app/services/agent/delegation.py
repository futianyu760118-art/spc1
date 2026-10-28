"""父 Agent 调用直属子 Agent：一次只读委派，结果直接返回父 Agent。"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent.agent import Agent
from app.models.agent.call import AgentCallLog
from app.models.basicdata.user import SysUser
from app.services.agent.capabilities import CONFIGURABLE_CAPABILITIES
from app.services.agent.context import AgentContext, load_agent_context
from app.services.agent.errors import AgentError
from app.services.agent.prompt import build_agent_system_prompt

logger = logging.getLogger(__name__)


class DelegationError(AgentError):
    pass


def _finish(
    call: AgentCallLog,
    started: float,
    *,
    status: str,
    error: Optional[str] = None,
    result_summary: Optional[str] = None,
) -> None:
    call.status = status
    call.error = (error or "")[:2000] or None
    call.result_summary = (result_summary or "")[:4000] or None
    call.duration_ms = int((time.perf_counter() - started) * 1000)


async def _resolve_target(
    db: AsyncSession,
    parent_ctx: AgentContext,
    *,
    target_user_id: int,
    capability: str,
) -> tuple[Agent, SysUser, AgentContext]:
    target_user = await db.get(SysUser, int(target_user_id))
    if not target_user or not target_user.is_active:
        raise DelegationError("目标用户不存在或已停用", 404)
    target_agent = (await db.execute(
        select(Agent).where(Agent.user_id == int(target_user.id))
    )).scalars().first()
    if not target_agent:
        raise DelegationError("目标用户还没有智能体", 404)
    if int(target_agent.parent_agent_id or 0) != int(parent_ctx.agent.id):
        raise DelegationError("只能委派给直属子智能体", 403)
    if target_agent.status != "active":
        raise DelegationError("目标子智能体已禁用", 403)
    capability_def = CONFIGURABLE_CAPABILITIES.get(capability)
    if capability_def is None:
        raise DelegationError(f"能力码不可用：{capability}", 400)
    if not capability_def.read_only:
        raise DelegationError("子智能体调用仅支持只读能力；写操作请由父智能体确认后执行", 403)
    target_ctx = await load_agent_context(db, target_user, use_cache=False)
    if capability not in target_ctx.effective_capabilities:
        available = sorted(
            code for code in target_ctx.effective_capabilities
            if code in CONFIGURABLE_CAPABILITIES and CONFIGURABLE_CAPABILITIES[code].read_only
        )
        raise DelegationError(
            f"目标子智能体不具备能力 {capability}；可用只读能力：{', '.join(available) or '无'}",
            403,
        )
    return target_agent, target_user, target_ctx


def _child_prompt(
    target_ctx: AgentContext,
    *,
    capability: str,
    instruction: str,
    context: Dict[str, Any],
) -> str:
    from app.services.assistant.orchestrator import resolve_system_prompt

    base = resolve_system_prompt(None, set())
    prompt = build_agent_system_prompt(
        base,
        target_ctx,
        delegation_context_text=(
            f"上级智能体委派能力：{capability}\n"
            f"任务：{instruction}\n"
            f"上下文：{json.dumps(context, ensure_ascii=False, default=str)[:4000]}"
        ),
        delegated=True,
    )
    return prompt


async def delegate_task(
    db: AsyncSession,
    *,
    parent_ctx: AgentContext,
    target_user_id: int,
    capability: str,
    instruction: str,
    context: Dict[str, Any],
    trace_id: str,
    delegation_depth: int,
    max_delegation_depth: int,
) -> Dict[str, Any]:
    """执行一次子智能体委派；失败返回 ok=False，不向父对话抛异常。"""
    started = time.perf_counter()
    call = AgentCallLog(
        trace_id=trace_id or "",
        caller_agent_id=int(parent_ctx.agent.id),
        caller_user_id=int(parent_ctx.user.id),
        capability=capability,
        instruction_summary=instruction[:500],
        status="running",
        depth=int(delegation_depth),
    )
    db.add(call)
    await db.flush()

    if delegation_depth >= int(max_delegation_depth):
        _finish(call, started, status="rejected", error="委派层级超过上限")
        await db.flush()
        return {"ok": False, "error": "委派层级超过上限"}

    try:
        target_agent, target_user, target_ctx = await _resolve_target(
            db, parent_ctx, target_user_id=target_user_id, capability=capability,
        )
        call.callee_agent_id = int(target_agent.id)
        call.callee_user_id = int(target_user.id)
        await db.flush()

        prompt = _child_prompt(
            target_ctx, capability=capability, instruction=instruction, context=context,
        )
        child_trace = f"{trace_id}:delegate:{call.id}"
        text_parts: list[str] = []
        done_data: Optional[Dict[str, Any]] = None
        timeout = max(int(get_settings().AGENT_DELEGATION_TIMEOUT_SECONDS), 10)

        from app.services.assistant.orchestrator import run_reaction

        async with asyncio.timeout(timeout):
            async for event, data in run_reaction(
                instruction,
                [],
                system_prompt=prompt,
                model_override=None,
                temperature=0.2,
                max_tokens=4096,
                max_tool_rounds=4,
                max_agent_calls=4,
                disabled_tools={"call_order_agent", "hub_query"},
                session_id="",
                trace_id=child_trace,
                user_id=str(target_user.id),
                provider_name="",
                stream_final=False,
                include_order_tool=False,
                gap_notify=False,
                db=db,
                agent_context=target_ctx,
                delegation_depth=delegation_depth + 1,
                max_delegation_depth=max_delegation_depth,
            ):
                if event == "delta":
                    text_parts.append(data.get("text") or "")
                elif event == "done":
                    done_data = data
                elif event == "error":
                    raise DelegationError(data.get("message") or "子智能体执行失败")
                elif event == "confirmation_required":
                    raise DelegationError("子智能体尝试写操作，已拒绝；请由父智能体走写确认")

        if done_data and done_data.get("failed"):
            raise DelegationError(done_data.get("partial_reason") or "子智能体执行失败")
        summary = ((done_data or {}).get("text") or "").strip() or "".join(text_parts).strip()
        if not summary:
            raise DelegationError("子智能体未返回结果")
        diagnostics = (done_data or {}).get("diagnostics") or {}
        result = {
            "ok": True,
            "target": {
                "agent_id": int(target_agent.id),
                "user_id": int(target_user.id),
                "name": target_agent.display_name or target_user.display_name or target_user.username,
            },
            "capability": capability,
            "summary": summary,
            "steps": (done_data or {}).get("steps") or [],
            "usage": {"total_tokens": diagnostics.get("total_tokens")},
        }
        _finish(call, started, status="success", result_summary=summary)
        await db.flush()
        return result
    except TimeoutError:
        _finish(call, started, status="timeout", error="子智能体调用超时")
        await db.flush()
        return {"ok": False, "error": "子智能体调用超时"}
    except DelegationError as exc:
        _finish(call, started, status="rejected", error=exc.message)
        await db.flush()
        return {"ok": False, "error": exc.message}
    except Exception as exc:  # noqa: BLE001 — 委派失败不打断父对话
        logger.warning("[delegation] 子智能体调用失败 trace=%s: %s", trace_id, exc)
        _finish(call, started, status="failed", error=str(exc))
        await db.flush()
        return {"ok": False, "error": f"子智能体调用失败：{exc}"}
