"""智能体团队：勾选/移除/候选（开放范围过滤）/成员清单。"""

from typing import List

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent.agent import Agent
from app.models.agent.team import AgentTeamMember
from app.models.basicdata.user import SysUser
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
