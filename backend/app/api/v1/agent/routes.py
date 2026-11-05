"""智能体中心 API：智能体目录管理、我的团队勾选、会话与调用记录。"""

import logging
from datetime import datetime, timedelta
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.agent.agent import Agent
from app.models.agent.call import AgentCallLog
from app.models.agent.conversation import AgentConversation
from app.models.agent.team import AgentTeamMember
from app.models.basicdata.ai_agent import AssistantRun
from app.models.basicdata.user import SysUser
from app.services.agent import conversation as conversation_service
from app.services.agent import sequence, team as team_service
from app.services.agent.capabilities import (
    ALL_CONFIGURABLE_CODES,
    CONFIGURABLE_CAPABILITIES,
    public_catalog,
)
from app.services.agent.context import load_user_context
from app.services.agent.skills import (
    MAX_SKILLS_PER_AGENT,
    load_agent_skills,
    sync_agent_skill_bindings,
    validate_skill_ids,
)

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


def _agent_brief(agent: Agent, skills: Optional[List[dict]] = None) -> dict:
    capabilities = [
        {"code": code, "name": (
            CONFIGURABLE_CAPABILITIES[code].name
            if code in CONFIGURABLE_CAPABILITIES else code
        )}
        for code in (agent.capability_codes or [])
    ]
    skill_items = skills or []
    return {
        "id": agent.id,
        "agent_no": agent.agent_no,
        "name": agent.display_name,
        "capabilities": capabilities,
        "skills": skill_items,
        "skill_count": len(skill_items),
        "scope_type": agent.scope_type,
        "scope_role_ids": agent.scope_role_ids or [],
        "description": agent.description,
        "status": agent.status,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def _capability_items(capabilities: set) -> List[dict]:
    return [
        {"code": code, "name": CONFIGURABLE_CAPABILITIES[code].name,
         "category": CONFIGURABLE_CAPABILITIES[code].category}
        for code in sorted(capabilities) if code in CONFIGURABLE_CAPABILITIES
    ]


async def _call_items(db: AsyncSession, rows: List[AgentCallLog]) -> List[dict]:
    agent_ids = {int(row.callee_agent_id) for row in rows if row.callee_agent_id}
    agents = {}
    if agent_ids:
        for agent in (await db.execute(
            select(Agent).where(Agent.id.in_(agent_ids))
        )).scalars().all():
            agents[int(agent.id)] = agent.display_name
    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "trace_id": row.trace_id,
            "callee": {
                "agent_id": int(row.callee_agent_id) if row.callee_agent_id else None,
                "name": agents.get(int(row.callee_agent_id)) if row.callee_agent_id else None,
            },
            "capability": row.capability,
            "instruction_summary": row.instruction_summary,
            "status": row.status,
            "result_summary": row.result_summary,
            "error": row.error,
            "duration_ms": row.duration_ms,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return items


class TeamCheckIn(BaseModel):
    agent_id: int


class BindUsersIn(BaseModel):
    agent_ids: List[int]
    user_ids: List[int]
    action: Literal["bind", "unbind"] = "bind"


class AgentUpsertIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    capabilities: List[str] = Field(default_factory=list)
    scope_type: str = "all"
    scope_role_ids: Optional[List[int]] = None
    description: Optional[str] = Field(default=None, max_length=500)
    status: str = "active"
    skill_ids: List[int] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("智能体名称不能为空白")
        return stripped

    @field_validator("capabilities")
    @classmethod
    def capabilities_normalized(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(code.strip() for code in value if code.strip()))


# ───────────────────────────── 我的 ─────────────────────────────

@router.get("/me")
async def my_agent(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_user_context(db, user, use_cache=False)
        week_start = datetime.now() - timedelta(days=7)
        usage = (await db.execute(
            select(func.count(AssistantRun.id), func.coalesce(func.sum(AssistantRun.total_tokens), 0))
            .where(AssistantRun.user_id == str(user.id), AssistantRun.created_at >= week_start)
        )).first()
        calls = (await db.execute(
            select(AgentCallLog)
            .where(AgentCallLog.caller_user_id == user.id)
            .order_by(AgentCallLog.id.desc())
            .limit(5)
        )).scalars().all()
        return _ok({
            "user": {"id": user.id, "username": user.username, "display_name": user.display_name},
            "display_name": ctx.display_name,
            "team_size": len(ctx.members),
            "effective_capabilities": _capability_items(ctx.effective_capabilities),
            "skills": [
                {
                    "id": skill.skill_id,
                    "name": skill.name,
                    "description": skill.description,
                    "agent_id": skill.agent_id,
                    "agent_name": skill.agent_name,
                    "has_executor": skill.has_executor,
                }
                for skill in ctx.skills
            ],
            "usage_7d": {
                "runs": int(usage[0] or 0) if usage else 0,
                "total_tokens": int(usage[1] or 0) if usage else 0,
            },
            "capability_catalog": public_catalog(),
            "recent_calls": await _call_items(db, calls),
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
        rows = (await db.execute(
            select(AgentCallLog)
            .where(AgentCallLog.caller_user_id == user.id)
            .order_by(AgentCallLog.id.desc())
            .limit(limit)
        )).scalars().all()
        return _ok({"items": await _call_items(db, rows)})
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
        return _ok(await conversation_service.list_conversations(
            db, user_id=user.id, page=page, page_size=page_size,
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
        conversation = await conversation_service.get_owned_conversation(
            db, conversation_id, user_id=user.id,
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
        conversation = await conversation_service.get_owned_conversation(
            db, conversation_id, user_id=user.id,
        )
        return _ok(await conversation_service.archive_conversation(db, conversation))
    except Exception as exc:
        return _capture(exc)


# ───────────────────────────── 团队 ─────────────────────────────

@router.get("/me/team")
async def my_team(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.assistant", "read")),
):
    try:
        user = await _load_user(db, current_user)
        items = await team_service.list_my_team(db, user.id)
        return _ok({"items": items, "total": len(items)})
    except Exception as exc:
        return _capture(exc)


@router.get("/me/team/candidates")
async def team_candidates(
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.assistant", "read")),
):
    try:
        user = await _load_user(db, current_user)
        return _ok({"items": await team_service.list_candidates(db, user, keyword)})
    except Exception as exc:
        return _capture(exc)


@router.post("/me/team")
async def add_team_member(
    body: TeamCheckIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.assistant", "read")),
):
    try:
        user = await _load_user(db, current_user)
        result = await team_service.check_member(db, user, body.agent_id)
        return _ok(result, "已加入团队")
    except Exception as exc:
        return _capture(exc)


@router.delete("/me/team/{agent_id}")
async def remove_team_member(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.assistant", "read")),
):
    try:
        user = await _load_user(db, current_user)
        result = await team_service.uncheck_member(db, user.id, agent_id)
        return _ok(result, "已移出团队")
    except Exception as exc:
        return _capture(exc)


# ───────────────────────────── 能力目录 ─────────────────────────────

@router.get("/capabilities")
async def capability_catalog(
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    return _ok({"items": public_catalog()})


# ───────────────────────────── 管理员 ─────────────────────────────

def _validate_upsert(body: AgentUpsertIn) -> Optional[str]:
    unknown = [code for code in body.capabilities if code not in ALL_CONFIGURABLE_CODES]
    if unknown:
        return f"未知能力：{'、'.join(unknown)}"
    if len(set(body.skill_ids or [])) > MAX_SKILLS_PER_AGENT:
        return f"每个智能体最多绑定 {MAX_SKILLS_PER_AGENT} 个技能"
    if body.scope_type not in ("all", "roles"):
        return "scope_type 只能为 all 或 roles"
    if body.scope_type == "roles" and not body.scope_role_ids:
        return "scope_type=roles 时必须提供 scope_role_ids"
    if body.status not in ("active", "disabled"):
        return "status 只能为 active 或 disabled"
    return None


@router.get("/admin/agents")
async def admin_agents(
    keyword: str = "",
    capability: str = "",
    status: str = "",
    scope: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        conditions = []
        if status:
            conditions.append(Agent.status == status)
        if capability:
            conditions.append(Agent.capability_codes.contains([capability]))
        if scope:
            conditions.append(Agent.scope_type == scope)
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(Agent.display_name.ilike(like), Agent.agent_no.ilike(like)))
        total = int((await db.execute(
            select(func.count(Agent.id)).where(*conditions)
        )).scalar() or 0)
        rows = (await db.execute(
            select(Agent).where(*conditions).order_by(Agent.id.asc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        skills_by_agent = await load_agent_skills(
            db, [agent.id for agent in rows], include_disabled=True,
        )
        items = []
        for agent in rows:
            teams_count = int((await db.execute(
                select(func.count(AgentTeamMember.id)).where(AgentTeamMember.agent_id == agent.id)
            )).scalar() or 0)
            items.append({
                **_agent_brief(agent, skills_by_agent.get(int(agent.id), [])),
                "teams_count": teams_count,
            })
        return _ok({"items": items, "total": total, "page": page, "page_size": page_size})
    except Exception as exc:
        return _capture(exc)


@router.post("/admin/agents")
async def create_agent(
    body: AgentUpsertIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        invalid = _validate_upsert(body)
        if invalid:
            return _err(invalid)
        operator = await _load_user(db, current_user)
        dup = (await db.execute(
            select(Agent).where(Agent.display_name == body.name.strip())
        )).scalars().first()
        if dup:
            return _err("已存在同名智能体")
        await validate_skill_ids(db, body.skill_ids)
        next_id = await sequence.next_serial_id(db, "agent")
        agent = Agent(
            id=next_id,
            agent_no=f"AG-{next_id:06d}",
            display_name=body.name.strip(),
            capability_codes=body.capabilities,
            scope_type=body.scope_type,
            scope_role_ids=body.scope_role_ids if body.scope_type == "roles" else None,
            description=body.description,
            status=body.status,
            created_by_user_id=operator.id,
        )
        db.add(agent)
        await db.flush()
        await sync_agent_skill_bindings(db, agent.id, body.skill_ids)
        skills = (await load_agent_skills(db, [agent.id], include_disabled=True)).get(int(agent.id), [])
        await log_audit(db, "agent", agent.id, "create", operator=operator.username)
        return _ok(_agent_brief(agent, skills), "已创建")
    except Exception as exc:
        return _capture(exc)


@router.put("/admin/agents/{agent_id}")
async def update_agent(
    agent_id: int,
    body: AgentUpsertIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        invalid = _validate_upsert(body)
        if invalid:
            return _err(invalid)
        agent = await db.get(Agent, agent_id)
        if not agent:
            return _err("智能体不存在", 404)
        dup = (await db.execute(
            select(Agent).where(Agent.display_name == body.name.strip(), Agent.id != agent_id)
        )).scalars().first()
        if dup:
            return _err("已存在同名智能体")
        await validate_skill_ids(db, body.skill_ids)
        agent.display_name = body.name.strip()
        agent.capability_codes = body.capabilities
        agent.scope_type = body.scope_type
        agent.scope_role_ids = body.scope_role_ids if body.scope_type == "roles" else None
        agent.description = body.description
        agent.status = body.status
        agent.config_version = int(agent.config_version or 1) + 1
        await sync_agent_skill_bindings(db, agent.id, body.skill_ids)
        skills = (await load_agent_skills(db, [agent.id], include_disabled=True)).get(int(agent.id), [])
        await db.flush()
        return _ok(_agent_brief(agent, skills), "已保存")
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
            "items": await _call_items(db, rows),
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


@router.get("/admin/users")
async def admin_users(
    keyword: str = "",
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        return _ok({"items": await team_service.admin_user_options(
            db, keyword=keyword, limit=limit,
        )})
    except Exception as exc:
        return _capture(exc)


@router.post("/admin/users/bind")
async def admin_bind_users(
    body: BindUsersIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        operator = await _load_user(db, current_user)
        result = await team_service.admin_bind_users(
            db,
            agent_ids=body.agent_ids,
            user_ids=body.user_ids,
            action=body.action,
            operator_id=int(operator.id),
        )
        summary = (
            f"agents={len(set(body.agent_ids))} users={len(set(body.user_ids))} "
            f"created={result['created']} removed={result['removed']} skipped={result['skipped']}"
        )
        await log_audit(
            db, "agent_team", 0, f"batch_{body.action}", field_name="batch",
            new_value=summary, operator=operator.username,
        )
        return _ok(result, "已绑定" if body.action == "bind" else "已解绑")
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
