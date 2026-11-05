"""智能体团队：勾选/移除/候选（开放范围过滤）/成员清单。"""

from collections import defaultdict
from typing import Dict, List

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent.agent import Agent
from app.models.agent.team import AgentTeamMember
from app.models.basicdata.user import SysRole, SysUser
from app.services.agent.capabilities import CONFIGURABLE_CAPABILITIES
from app.services.agent.errors import AgentError
from app.services.agent.notify import notify_user
from app.services.agent.skills import load_agent_skills


def _capability_items(agent: Agent) -> List[dict]:
    return [
        {"code": code, "name": CONFIGURABLE_CAPABILITIES[code].name}
        for code in (agent.capability_codes or [])
        if code in CONFIGURABLE_CAPABILITIES
    ]


async def get_visible_agent(db: AsyncSession, user: SysUser, agent_id: int) -> Agent:
    """加载对用户可见且 active 的智能体，否则抛错。"""
    agent = await db.get(Agent, int(agent_id))
    if not agent:
        raise AgentError("智能体不存在", 404)
    if agent.status != "active":
        raise AgentError("智能体已停用", 400)
    if not await is_visible(db, user, agent):
        raise AgentError("该智能体未对你开放", 403)
    return agent


async def is_visible(db: AsyncSession, user: SysUser, agent: Agent) -> bool:
    if agent.scope_type != "roles":
        return True
    role_ids = [int(r) for r in (agent.scope_role_ids or [])]
    return int(user.role_id or 0) in role_ids


async def list_my_team(db: AsyncSession, user_id: int) -> List[dict]:
    rows = (await db.execute(
        select(AgentTeamMember, Agent)
        .join(Agent, Agent.id == AgentTeamMember.agent_id)
        .where(AgentTeamMember.user_id == int(user_id))
        .order_by(AgentTeamMember.id.asc())
    )).all()
    skills_by_agent = await load_agent_skills(db, [agent.id for _, agent in rows])
    return [
        {
            "id": int(agent.id),
            "agent_no": agent.agent_no,
            "name": agent.display_name,
            "capabilities": _capability_items(agent),
            "skills": skills_by_agent.get(int(agent.id), []),
            "description": agent.description,
            "status": agent.status,
            "checked": True,
            "created_at": member.created_at.isoformat() if member.created_at else None,
        }
        for member, agent in rows
    ]


async def list_candidates(db: AsyncSession, user: SysUser, keyword: str = "") -> List[dict]:
    """可勾选列表：active + 对我可见 + 未勾选。"""
    checked = (await db.execute(
        select(AgentTeamMember.agent_id).where(AgentTeamMember.user_id == int(user.id))
    )).scalars().all()
    conditions = [Agent.status == "active"]
    if checked:
        conditions.append(Agent.id.notin_([int(a) for a in checked]))
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        conditions.append(or_(Agent.display_name.ilike(like), Agent.agent_no.ilike(like)))
    rows = (await db.execute(select(Agent).where(*conditions).order_by(Agent.id.asc()))).scalars().all()
    visible = []
    for agent in rows:
        if await is_visible(db, user, agent):
            visible.append(agent)
    skills_by_agent = await load_agent_skills(db, [agent.id for agent in visible])
    return [
        {
            "id": int(agent.id),
            "agent_no": agent.agent_no,
            "name": agent.display_name,
            "capabilities": _capability_items(agent),
            "skills": skills_by_agent.get(int(agent.id), []),
            "description": agent.description,
        }
        for agent in visible
    ]


async def check_member(db: AsyncSession, user: SysUser, agent_id: int) -> dict:
    agent = await get_visible_agent(db, user, agent_id)
    exists = (await db.execute(
        select(AgentTeamMember).where(
            AgentTeamMember.user_id == int(user.id),
            AgentTeamMember.agent_id == int(agent_id),
        )
    )).scalars().first()
    if exists:
        raise AgentError("该智能体已在你的团队中", 400)
    db.add(AgentTeamMember(user_id=int(user.id), agent_id=int(agent.id), created_by_user_id=int(user.id)))
    await db.flush()
    await notify_user(
        db,
        user_id=int(user.id),
        title="[智能体]团队成员已添加",
        content=f"智能体「{agent.display_name}」已加入你的团队，助手即刻获得其能力。",
        notif_type="agent_team",
        ref_type="agent",
        ref_id=agent.id,
    )
    return {"agent_id": int(agent.id), "name": agent.display_name}


async def uncheck_member(db: AsyncSession, user_id: int, agent_id: int) -> dict:
    member = (await db.execute(
        select(AgentTeamMember).where(
            AgentTeamMember.user_id == int(user_id),
            AgentTeamMember.agent_id == int(agent_id),
        )
    )).scalars().first()
    if not member:
        raise AgentError("该智能体不在你的团队中", 404)
    agent = await db.get(Agent, int(agent_id))
    await db.delete(member)
    await db.flush()
    await notify_user(
        db,
        user_id=int(user_id),
        title="[智能体]团队成员已移除",
        content=f"智能体「{agent.display_name if agent else agent_id}」已移出你的团队，其能力不再可用。",
        notif_type="agent_team",
        ref_type="agent",
        ref_id=int(agent_id),
    )
    return {"agent_id": int(agent_id)}


MAX_BIND_PAIRS = 10000
RESTRICTED_USER_ROLES = ("supplier", "api_caller", "share")


async def admin_user_options(
    db: AsyncSession, *, keyword: str = "", limit: int = 500
) -> List[dict]:
    conditions = [
        SysUser.is_active.is_(True),
        SysRole.role_code.notin_(RESTRICTED_USER_ROLES),
    ]
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        conditions.append(or_(SysUser.username.ilike(like), SysUser.display_name.ilike(like)))
    rows = (await db.execute(
        select(SysUser, SysRole)
        .join(SysRole, SysRole.id == SysUser.role_id)
        .where(*conditions)
        .order_by(SysUser.username.asc())
        .limit(max(1, min(int(limit), 1000)))
    )).all()
    return [
        {
            "id": int(user.id),
            "username": user.username,
            "display_name": user.display_name or user.username,
            "role_id": int(role.id) if role else None,
            "role_name": role.role_name if role else "",
        }
        for user, role in rows
    ]


async def _notify_team_bindings(
    db: AsyncSession, changes: Dict[int, List[str]], *, added: bool
) -> None:
    action = "添加" if added else "移除"
    for user_id, names in changes.items():
        preview = "、".join(names[:10])
        if len(names) > 10:
            preview += f" 等{len(names)}个"
        await notify_user(
            db,
            user_id=int(user_id),
            title=f"[智能体]管理员已{action}团队成员",
            content=f"管理员为你{action}了智能体：{preview}。",
            notif_type="agent_team",
            ref_type="agent",
            ref_id=0,
        )


async def admin_bind_users(
    db: AsyncSession,
    *,
    agent_ids: List[int],
    user_ids: List[int],
    action: str = "bind",
    operator_id: int | None = None,
) -> dict:
    """管理员批量绑定/解绑智能体与用户（agent × user 笛卡尔积）。"""
    if action not in ("bind", "unbind"):
        raise AgentError("action 只能为 bind 或 unbind")
    agent_ids = list(dict.fromkeys(int(item) for item in (agent_ids or [])))
    user_ids = list(dict.fromkeys(int(item) for item in (user_ids or [])))
    if not agent_ids or not user_ids:
        raise AgentError("至少选择一个智能体和一个用户")
    if len(agent_ids) * len(user_ids) > MAX_BIND_PAIRS:
        raise AgentError(f"单次批量最多 {MAX_BIND_PAIRS} 个绑定关系")

    agents = (await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))).scalars().all()
    users = (await db.execute(select(SysUser).where(SysUser.id.in_(user_ids)))).scalars().all()
    agents_by_id = {int(item.id): item for item in agents}
    users_by_id = {int(item.id): item for item in users}
    errors: List[str] = []
    for agent_id in agent_ids:
        if agent_id not in agents_by_id:
            errors.append(f"智能体不存在：{agent_id}")
    for user_id in user_ids:
        if user_id not in users_by_id:
            errors.append(f"用户不存在：{user_id}")
    valid_agents = [agents_by_id[item] for item in agent_ids if item in agents_by_id]
    valid_users = [users_by_id[item] for item in user_ids if item in users_by_id]

    existing_rows = (await db.execute(
        select(AgentTeamMember.user_id, AgentTeamMember.agent_id).where(
            AgentTeamMember.user_id.in_([int(u.id) for u in valid_users]),
            AgentTeamMember.agent_id.in_([int(a.id) for a in valid_agents]),
        )
    )).all()
    existing = {(int(user_id), int(agent_id)) for user_id, agent_id in existing_rows}
    requested_pairs = len(valid_agents) * len(valid_users)

    if action == "unbind":
        removed_by_user: Dict[int, List[str]] = defaultdict(list)
        removed = 0
        for user in valid_users:
            for agent in valid_agents:
                if (int(user.id), int(agent.id)) in existing:
                    removed_by_user[int(user.id)].append(agent.display_name)
                    removed += 1
        if removed:
            await db.execute(delete(AgentTeamMember).where(
                AgentTeamMember.user_id.in_([int(u.id) for u in valid_users]),
                AgentTeamMember.agent_id.in_([int(a.id) for a in valid_agents]),
            ))
            await db.flush()
            await _notify_team_bindings(db, removed_by_user, added=False)
        return {
            "action": action,
            "created": 0,
            "removed": removed,
            "skipped": requested_pairs - removed,
            "errors": errors,
            "skipped_details": [],
        }

    new_pairs: List[dict] = []
    added_by_user: Dict[int, List[str]] = defaultdict(list)
    skipped_details: List[dict] = []
    for agent in valid_agents:
        scope_roles = {int(item) for item in (agent.scope_role_ids or [])}
        for user in valid_users:
            if not user.is_active:
                reason = "用户已停用"
            elif agent.status != "active":
                reason = "智能体已停用"
            elif agent.scope_type == "roles" and int(user.role_id or 0) not in scope_roles:
                reason = "用户角色不在智能体开放范围"
            elif (int(user.id), int(agent.id)) in existing:
                reason = "已绑定"
            else:
                reason = ""
            if reason:
                if len(skipped_details) < 50:
                    skipped_details.append({
                        "agent_id": int(agent.id),
                        "user_id": int(user.id),
                        "reason": reason,
                    })
                continue
            new_pairs.append({
                "user_id": int(user.id),
                "agent_id": int(agent.id),
                "created_by_user_id": operator_id,
            })
            added_by_user[int(user.id)].append(agent.display_name)

    created = 0
    if new_pairs:
        result = await db.execute(
            pg_insert(AgentTeamMember)
            .values(new_pairs)
            .on_conflict_do_nothing(index_elements=["user_id", "agent_id"])
        )
        await db.flush()
        rowcount = getattr(result, "rowcount", None)
        created = int(rowcount) if rowcount is not None and rowcount >= 0 else len(new_pairs)
        if created:
            await _notify_team_bindings(db, added_by_user, added=True)
    return {
        "action": action,
        "created": created,
        "removed": 0,
        "skipped": requested_pairs - created,
        "errors": errors,
        "skipped_details": skipped_details,
    }
