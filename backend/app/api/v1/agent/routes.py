"""智能体中心 API：我的智能体、团队层级、能力配置与委派调用记录。"""

import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.agent.agent import Agent
from app.models.agent.call import AgentCallLog
from app.models.agent.conversation import AgentConversation
from app.models.basicdata.ai_agent import AssistantRun
from app.models.basicdata.user import SysUser
from app.services.agent import conversation as conversation_service
from app.services.agent import hierarchy, policy
from app.services.agent.capabilities import (
    CONFIGURABLE_CAPABILITIES,
    baseline_capabilities,
    public_catalog,
)
from app.services.agent.context import load_agent_context

logger = logging.getLogger(__name__)

router = APIRouter()


def _user_id(current_user: dict) -> int:
    return int(current_user.get("user_id") or current_user.get("sub"))


async def _load_user(db: AsyncSession, current_user: dict) -> SysUser:
    user = await db.get(SysUser, _user_id(current_user))
    if not user:
        raise ValueError("用户不存在")
    return user


def _ok(data: Any = None, message: str = "") -> dict:
    return {"code": 0, "message": message, "data": data}


def _err(message: str, code: int = 400) -> dict:
    return {"code": code, "message": message, "data": None}


def _capture(exc: Exception) -> dict:
    status = getattr(exc, "status_code", None)
    message = getattr(exc, "message", None) or str(exc)
    if status is None:
        logger.exception("[agent-api] 未预期异常: %s", exc)
    return _err(message, int(status or 400))


def _agent_brief(agent: Agent, user: SysUser) -> dict:
    return {
        "id": agent.id,
        "agent_no": agent.agent_no,
        "user_id": agent.user_id,
        "username": user.username,
        "display_name": agent.display_name,
        "status": agent.status,
        "parent_agent_id": agent.parent_agent_id,
        "config_version": agent.config_version,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def _capability_items(capabilities: set) -> List[dict]:
    return [
        {"code": code, "name": CONFIGURABLE_CAPABILITIES[code].name,
         "category": CONFIGURABLE_CAPABILITIES[code].category}
        for code in sorted(capabilities) if code in CONFIGURABLE_CAPABILITIES
    ]


async def _agent_label(db: AsyncSession, agent_id: Optional[int]) -> dict:
    if not agent_id:
        return {}
    agent = await db.get(Agent, int(agent_id))
    if not agent:
        return {"agent_id": int(agent_id)}
    user = await db.get(SysUser, int(agent.user_id))
    return {
        "agent_id": int(agent.id),
        "name": agent.display_name or (user.display_name if user else None) or (user.username if user else None),
        "username": user.username if user else None,
        "user_id": int(agent.user_id),
    }


async def _call_items(db: AsyncSession, rows: List[AgentCallLog], current_agent_id: int) -> List[dict]:
    items = []
    for row in rows:
        caller = await _agent_label(db, row.caller_agent_id)
        callee = await _agent_label(db, row.callee_agent_id)
        items.append({
            "id": row.id,
            "trace_id": row.trace_id,
            "caller": caller,
            "callee": callee,
            "direction": (
                "outgoing" if int(row.caller_agent_id) == int(current_agent_id) else "incoming"
            ) if current_agent_id else "",
            "capability": row.capability,
            "instruction_summary": row.instruction_summary,
            "status": row.status,
            "result_summary": row.result_summary,
            "error": row.error,
            "duration_ms": row.duration_ms,
            "depth": row.depth,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return items


class AddMemberIn(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None


class PolicyIn(BaseModel):
    granted: Optional[List[str]] = None
    disabled: Optional[List[str]] = None
    reason: str = ""


class HierarchyIn(BaseModel):
    action: str
    new_parent_id: Optional[int] = None
    reason: str = ""


# ───────────────────────────── 我的 ─────────────────────────────

@router.get("/me")
async def my_agent(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        week_start = datetime.now() - timedelta(days=7)
        usage = (await db.execute(
            select(func.count(AssistantRun.id), func.coalesce(func.sum(AssistantRun.total_tokens), 0))
            .where(AssistantRun.user_id == str(user.id), AssistantRun.created_at >= week_start)
        )).first()
        parent = await db.get(Agent, ctx.agent.parent_agent_id) if ctx.agent.parent_agent_id else None
        calls = (await db.execute(
            select(AgentCallLog)
            .where(or_(
                AgentCallLog.caller_agent_id == ctx.agent.id,
                AgentCallLog.callee_agent_id == ctx.agent.id,
            ))
            .order_by(AgentCallLog.id.desc())
            .limit(5)
        )).scalars().all()
        return _ok({
            "agent": _agent_brief(ctx.agent, user),
            "display_name": ctx.display_name,
            "parent_agent_id": ctx.agent.parent_agent_id,
            "parent_display_name": parent.display_name if parent else None,
            "is_supervisor": ctx.is_supervisor,
            "children_count": len(ctx.children),
            "effective_capabilities": _capability_items(ctx.effective_capabilities),
            "policy": policy.normalize_policy(ctx.agent.capability_policy),
            "usage_7d": {
                "runs": int(usage[0] or 0) if usage else 0,
                "total_tokens": int(usage[1] or 0) if usage else 0,
            },
            "capability_catalog": public_catalog(),
            "recent_calls": await _call_items(db, calls, int(ctx.agent.id)),
        })
    except Exception as exc:
        return _capture(exc)


@router.get("/me/calls")
async def my_calls(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        rows = (await db.execute(
            select(AgentCallLog)
            .where(or_(
                AgentCallLog.caller_agent_id == ctx.agent.id,
                AgentCallLog.callee_agent_id == ctx.agent.id,
            ))
            .order_by(AgentCallLog.id.desc())
            .limit(limit)
        )).scalars().all()
        return _ok({"items": await _call_items(db, rows, int(ctx.agent.id))})
    except Exception as exc:
        return _capture(exc)


@router.get("/me/conversations")
async def my_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await conversation_service.list_conversations(
            db, agent_id=ctx.agent.id, user_id=user.id, page=page, page_size=page_size,
        ))
    except Exception as exc:
        return _capture(exc)


@router.get("/me/conversations/{conversation_id}")
async def my_conversation_detail(
    conversation_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        conversation = await conversation_service.get_owned_conversation(
            db, conversation_id, user_id=user.id, agent_id=ctx.agent.id,
        )
        return _ok(await conversation_service.conversation_messages(db, conversation, limit))
    except Exception as exc:
        return _capture(exc)


@router.post("/me/conversations/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        conversation = await conversation_service.get_owned_conversation(
            db, conversation_id, user_id=user.id, agent_id=ctx.agent.id,
        )
        return _ok(await conversation_service.archive_conversation(db, conversation))
    except Exception as exc:
        return _capture(exc)


# ───────────────────────────── 团队 ─────────────────────────────

@router.get("/me/team")
async def my_team(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        items = []
        for child in ctx.children:
            child_user = await db.get(SysUser, child.user_id)
            child_agent = await db.get(Agent, child.agent_id)
            if not child_user or not child_agent:
                continue
            items.append({
                **_agent_brief(child_agent, child_user),
                "name": child.display_name,
                "username": child.username,
                "capabilities": [
                    {"code": code, "name": CONFIGURABLE_CAPABILITIES[code].name}
                    for code in child.capabilities
                    if code in CONFIGURABLE_CAPABILITIES
                ],
            })
        return _ok({"items": items, "total": len(items)})
    except Exception as exc:
        return _capture(exc)


@router.post("/me/team")
async def add_team_member(
    body: AddMemberIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        result = await hierarchy.add_subordinate(
            db, ctx, user_id=body.user_id, username=body.username or "",
        )
        return _ok(result, "已添加并通知对方")
    except Exception as exc:
        return _capture(exc)


@router.delete("/me/team/{agent_id}")
async def remove_team_member(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        result = await hierarchy.remove_subordinate(db, ctx, agent_id)
        return _ok(result, "已移除并通知对方")
    except Exception as exc:
        return _capture(exc)


@router.get("/me/team/candidates")
async def team_candidates(
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        await _load_user(db, current_user)
        return _ok({"items": await hierarchy.list_candidates(db, keyword)})
    except Exception as exc:
        return _capture(exc)


@router.get("/me/team/{agent_id}")
async def team_member_detail(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        child = await db.get(Agent, agent_id)
        if not child or int(child.parent_agent_id or 0) != int(ctx.agent.id):
            return _err("只能查看直属子智能体", 403)
        return _ok(await _agent_detail(db, child, ctx))
    except Exception as exc:
        return _capture(exc)


@router.put("/me/team/{agent_id}/policy")
async def update_team_policy(
    agent_id: int,
    body: PolicyIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        target = await db.get(Agent, agent_id)
        if not target:
            return _err("智能体不存在", 404)
        saved = await policy.update_agent_policy(
            db, operator_ctx=ctx, target_agent=target,
            granted=body.granted, disabled=body.disabled,
            reason=body.reason, is_admin=False,
        )
        return _ok(saved, "配置已保存并通知对方")
    except Exception as exc:
        return _capture(exc)


# ───────────────────────────── 管理员 ─────────────────────────────

async def _agent_detail(db: AsyncSession, target: Agent, viewer_ctx) -> dict:
    target_user = await db.get(SysUser, target.user_id)
    if not target_user:
        raise ValueError("目标用户不存在")
    target_ctx = await load_agent_context(db, target_user, use_cache=False)
    target_policy = policy.normalize_policy(target.capability_policy)
    role_baseline = baseline_capabilities(target_ctx.permissions)
    effective = target_ctx.effective_capabilities
    catalog = []
    for item in public_catalog():
        code = item["code"]
        if not item.get("grantable"):
            continue
        catalog.append({
            **item,
            "role_owned": code in role_baseline,
            "granted": code in (target_policy.get("granted") or []),
            "disabled": code in (target_policy.get("disabled") or []),
            "effective": code in effective,
            "grantable_now": code in viewer_ctx.effective_capabilities,
        })
    return {
        "agent": _agent_brief(target, target_user),
        "policy": target_policy,
        "effective_capabilities": _capability_items(effective),
        "role_baseline": _capability_items(role_baseline),
        "grantable": _capability_items(viewer_ctx.effective_capabilities),
        "catalog": catalog,
    }


@router.get("/admin/agents")
async def admin_agents(
    keyword: str = "",
    status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        conditions = []
        if status:
            conditions.append(Agent.status == status)
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(SysUser.username.ilike(like), SysUser.display_name.ilike(like),
                                  Agent.agent_no.ilike(like)))
        total = int((await db.execute(
            select(func.count(Agent.id)).select_from(Agent)
            .join(SysUser, SysUser.id == Agent.user_id).where(*conditions)
        )).scalar() or 0)
        rows = (await db.execute(
            select(Agent, SysUser).join(SysUser, SysUser.id == Agent.user_id)
            .where(*conditions).order_by(Agent.id.asc())
            .offset((page - 1) * page_size).limit(page_size)
        )).all()
        items = []
        for agent, user in rows:
            child_count = int((await db.execute(
                select(func.count(Agent.id)).where(Agent.parent_agent_id == agent.id)
            )).scalar() or 0)
            items.append({
                **_agent_brief(agent, user),
                "children_count": child_count,
                "policy": policy.normalize_policy(agent.capability_policy),
            })
        return _ok({"items": items, "total": total, "page": page, "page_size": page_size})
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/agents/{agent_id}")
async def admin_agent_detail(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        actor = await _load_user(db, current_user)
        ctx = await load_agent_context(db, actor, use_cache=False)
        target = await db.get(Agent, agent_id)
        if not target:
            return _err("智能体不存在", 404)
        return _ok(await _agent_detail(db, target, ctx))
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/calls")
async def admin_calls(
    keyword: str = "",
    status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        conditions = []
        if status:
            conditions.append(AgentCallLog.status == status)
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(
                AgentCallLog.capability.ilike(like),
                AgentCallLog.instruction_summary.ilike(like),
                AgentCallLog.result_summary.ilike(like),
            ))
        total = int((await db.execute(
            select(func.count(AgentCallLog.id)).where(*conditions)
        )).scalar() or 0)
        rows = (await db.execute(
            select(AgentCallLog).where(*conditions)
            .order_by(AgentCallLog.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return _ok({
            "items": await _call_items(db, rows, 0),
            "total": total, "page": page, "page_size": page_size,
        })
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        agent_count = int((await db.execute(select(func.count(Agent.id)))).scalar() or 0)
        active_agents = int((await db.execute(
            select(func.count(Agent.id)).where(Agent.status == "active")
        )).scalar() or 0)
        call_rows = (await db.execute(
            select(AgentCallLog.status, func.count(AgentCallLog.id)).group_by(AgentCallLog.status)
        )).all()
        return _ok({
            "agents": agent_count,
            "active_agents": active_agents,
            "calls_by_status": {row[0]: int(row[1]) for row in call_rows},
        })
    except Exception as exc:
        return _capture(exc)


@router.put("/admin/agents/{agent_id}/hierarchy")
async def admin_hierarchy(
    agent_id: int,
    body: HierarchyIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        actor = await _load_user(db, current_user)
        result = await hierarchy.admin_change_hierarchy(
            db, actor=actor, target_agent_id=agent_id,
            action=body.action, new_parent_id=body.new_parent_id, reason=body.reason,
        )
        return _ok(result)
    except Exception as exc:
        return _capture(exc)


@router.put("/admin/agents/{agent_id}/policy")
async def admin_policy(
    agent_id: int,
    body: PolicyIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        target = await db.get(Agent, agent_id)
        if not target:
            return _err("智能体不存在", 404)
        saved = await policy.update_agent_policy(
            db, operator_ctx=ctx, target_agent=target,
            granted=body.granted, disabled=body.disabled,
            reason=body.reason, is_admin=True,
        )
        return _ok(saved, "配置已保存并通知对方")
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/conversations/{conversation_id}")
async def admin_conversation(
    conversation_id: int,
    reason: str = Query(..., min_length=2),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        actor = await _load_user(db, current_user)
        conversation = await db.get(AgentConversation, conversation_id)
        if not conversation:
            return _err("会话不存在", 404)
        target_user = await db.get(SysUser, conversation.user_id)
        target_label = (
            f"{target_user.username}(id={target_user.id})" if target_user else f"id={conversation.user_id}"
        )
        await log_audit(
            db, "agent_conversation", conversation.id, "view",
            field_name="reason", new_value=f"{reason}；目标用户 {target_label}",
            operator=actor.display_name or actor.username,
        )
        data = await conversation_service.conversation_messages(db, conversation, limit)
        data.update({
            "target_user_id": conversation.user_id,
            "target_username": target_user.username if target_user else None,
            "reason": reason,
            "viewed_by": actor.username,
        })
        return _ok(data)
    except Exception as exc:
        return _capture(exc)
