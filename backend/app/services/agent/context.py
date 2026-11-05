"""UserContext：用户身份、团队智能体清单、团队能力并集与工具可见性。"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import merge_role_permission_additions
from app.models.agent.agent import Agent
from app.models.agent.team import AgentTeamMember
from app.models.basicdata.user import SysRole, SysUser
from app.services.agent import cache
from app.services.agent.capabilities import allowed_tool_names
from app.services.agent.skills import TeamSkillInfo, list_team_skill_briefs


@dataclass
class TeamMemberInfo:
    agent_id: int
    agent_no: str
    display_name: str
    capabilities: List[str]
    description: Optional[str]
    status: str
    config_version: int


@dataclass
class UserContext:
    user: SysUser
    role_code: str
    permissions: Dict[str, List[str]]
    members: List[TeamMemberInfo] = field(default_factory=list)
    effective_capabilities: Set[str] = field(default_factory=set)
    allowed_tools: Set[str] = field(default_factory=set)
    skills: List[TeamSkillInfo] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.user.display_name or self.user.username

    def members_by_capability(self, capability: str) -> List[TeamMemberInfo]:
        return [
            m for m in self.members
            if capability in m.capabilities and m.status == "active"
        ]

    def member_by_id(self, agent_id: int) -> Optional[TeamMemberInfo]:
        return next((m for m in self.members if m.agent_id == int(agent_id)), None)

    def skill_by_id(self, skill_id: int) -> Optional[TeamSkillInfo]:
        return next((s for s in self.skills if s.skill_id == int(skill_id)), None)


async def load_user_permissions(db: AsyncSession, user: SysUser) -> tuple[str, Dict[str, List[str]]]:
    row = (await db.execute(
        select(SysRole.role_code, SysRole.permissions).where(SysRole.id == user.role_id)
    )).first()
    role_code = row[0] if row else ""
    permissions = row[1] if row and isinstance(row[1], dict) else {}
    return role_code, merge_role_permission_additions(role_code, permissions)


async def list_team_members(db: AsyncSession, user_id: int) -> List[TeamMemberInfo]:
    rows = (await db.execute(
        select(AgentTeamMember, Agent)
        .join(Agent, Agent.id == AgentTeamMember.agent_id)
        .where(AgentTeamMember.user_id == int(user_id))
        .order_by(AgentTeamMember.id.asc())
    )).all()
    return [
        TeamMemberInfo(
            agent_id=int(agent.id),
            agent_no=agent.agent_no,
            display_name=agent.display_name,
            capabilities=[str(c) for c in (agent.capability_codes or [])],
            description=agent.description,
            status=agent.status,
            config_version=int(agent.config_version),
        )
        for _, agent in rows
    ]


async def load_user_context(
    db: AsyncSession,
    user: SysUser,
    *,
    use_cache: bool = True,
) -> UserContext:
    role_code, permissions = await load_user_permissions(db, user)
    members = await list_team_members(db, user.id)
    active = [m for m in members if m.status == "active"]
    skills = await list_team_skill_briefs(db, [m.agent_id for m in active])
    version_key = "-".join(f"{m.agent_id}v{m.config_version}" for m in sorted(active, key=lambda m: m.agent_id))
    cache_key = f"userctx:{user.id}:{version_key}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            effective, tools = set(cached["caps"]), set(cached["tools"])
            return UserContext(
                user=user, role_code=role_code, permissions=permissions,
                members=members, effective_capabilities=effective, allowed_tools=tools,
                skills=skills,
            )
    effective = {code for m in active for code in m.capabilities}
    tools = allowed_tool_names(effective)
    if use_cache:
        cache.set(cache_key, {"caps": set(effective), "tools": set(tools)})
    return UserContext(
        user=user, role_code=role_code, permissions=permissions,
        members=members, effective_capabilities=effective, allowed_tools=tools,
        skills=skills,
    )
