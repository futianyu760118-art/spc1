"""AgentContext：懒创建智能体、有效能力/范围、直属团队与工具可见性。"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import merge_role_permission_additions
from app.models.agent.agent import Agent
from app.models.basicdata.user import SysRole, SysUser
from app.services.agent import cache
from app.services.agent.sequence import next_serial_id
from app.services.agent.capabilities import (
    ALL_CONFIGURABLE_CODES,
    allowed_tool_names,
    resolve_capabilities,
)


@dataclass
class SubordinateInfo:
    agent_id: int
    user_id: int
    display_name: str
    username: str
    status: str
    capabilities: List[str] = field(default_factory=list)


@dataclass
class AgentContext:
    agent: Agent
    user: SysUser
    role_code: str
    permissions: Dict[str, List[str]]
    children: List[SubordinateInfo] = field(default_factory=list)
    effective_capabilities: Set[str] = field(default_factory=set)
    is_supervisor: bool = False
    can_manage_team: bool = False
    allowed_tools: Set[str] = field(default_factory=set)

    @property
    def display_name(self) -> str:
        return self.agent.display_name or f"{self.user.display_name or self.user.username}的智能体"

    def child_by_user_id(self, user_id: int) -> Optional[SubordinateInfo]:
        return next((c for c in self.children if c.user_id == int(user_id)), None)

    def child_by_name(self, name: str) -> Optional[SubordinateInfo]:
        value = (name or "").strip()
        if not value:
            return None
        exact = [c for c in self.children if value in (c.display_name, c.username)]
        if len(exact) == 1:
            return exact[0]
        fuzzy = [c for c in self.children if value in (c.display_name or "") or value in (c.username or "")]
        return fuzzy[0] if len(fuzzy) == 1 else None


async def load_user_permissions(db: AsyncSession, user: SysUser) -> tuple[str, Dict[str, List[str]]]:
    row = (await db.execute(
        select(SysRole.role_code, SysRole.permissions).where(SysRole.id == user.role_id)
    )).first()
    role_code = row[0] if row else ""
    permissions = row[1] if row and isinstance(row[1], dict) else {}
    return role_code, merge_role_permission_additions(role_code, permissions)


async def get_or_create_agent(
    db: AsyncSession,
    user: SysUser,
    *,
    created_by_user_id: Optional[int] = None,
) -> Agent:
    """按用户懒创建智能体；并发唯一冲突时回滚到保存点并复用既有行。"""
    existing = (await db.execute(
        select(Agent).where(Agent.user_id == user.id)
    )).scalars().first()
    if existing:
        return existing

    default_name = f"{user.display_name or user.username}的智能体"
    try:
        async with db.begin_nested():
            next_id = await next_serial_id(db, "agent")
            agent = Agent(
                id=next_id,
                agent_no=f"AG-{next_id:06d}",
                user_id=user.id,
                display_name=default_name[:64],
                status="active",
                capability_policy={"granted": [], "disabled": []},
                config_version=1,
                created_by_user_id=created_by_user_id,
            )
            db.add(agent)
            await db.flush()
        return agent
    except IntegrityError:
        existing = (await db.execute(
            select(Agent).where(Agent.user_id == user.id)
        )).scalars().first()
        if existing:
            return existing
        raise


async def get_or_create_agent_for_user_id(db: AsyncSession, user_id: int) -> Agent:
    user = await db.get(SysUser, int(user_id))
    if not user:
        raise ValueError(f"用户 {user_id} 不存在")
    return await get_or_create_agent(db, user)


async def _effective_capabilities(
    db: AsyncSession,
    agent: Agent,
    user: SysUser,
    permissions: Dict[str, List[str]],
    *,
    use_cache: bool,
) -> Set[str]:
    cache_key = f"agent:{agent.id}:v{agent.config_version}:caps"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return set(cached)

    parent_ceiling: Optional[Set[str]] = None
    if agent.parent_agent_id:
        parent = await db.get(Agent, agent.parent_agent_id)
        if parent:
            parent_user = await db.get(SysUser, parent.user_id)
            if parent_user:
                _, parent_perms = await load_user_permissions(db, parent_user)
                parent_ceiling = await _effective_capabilities(
                    db, parent, parent_user, parent_perms, use_cache=use_cache,
                )
        if parent_ceiling is None:
            parent_ceiling = set()
    else:
        parent_ceiling = set(ALL_CONFIGURABLE_CODES)

    effective = resolve_capabilities(permissions, agent.capability_policy, parent_ceiling)
    if use_cache:
        cache.set(cache_key, effective)
    return effective


async def list_subordinates(
    db: AsyncSession,
    agent: Agent,
    *,
    use_cache: bool = True,
) -> List[SubordinateInfo]:
    rows = (await db.execute(
        select(Agent, SysUser)
        .join(SysUser, SysUser.id == Agent.user_id)
        .where(Agent.parent_agent_id == agent.id)
        .order_by(Agent.id.asc())
    )).all()
    items: List[SubordinateInfo] = []
    for child, child_user in rows:
        _, child_permissions = await load_user_permissions(db, child_user)
        child_caps = await _effective_capabilities(
            db, child, child_user, child_permissions, use_cache=use_cache,
        )
        items.append(SubordinateInfo(
            agent_id=int(child.id),
            user_id=int(child.user_id),
            display_name=child.display_name or child_user.display_name or child_user.username,
            username=child_user.username,
            status=child.status,
            capabilities=sorted(child_caps),
        ))
    return items


async def load_agent_context(
    db: AsyncSession,
    user: SysUser,
    *,
    use_cache: bool = True,
) -> AgentContext:
    """构建每轮对话/API 所需的 AgentContext。"""
    agent = await get_or_create_agent(db, user, created_by_user_id=user.id)
    role_code, permissions = await load_user_permissions(db, user)
    children = await list_subordinates(db, agent, use_cache=use_cache)
    is_supervisor = any(c.status == "active" for c in children)
    can_manage_team = role_code not in ("supplier", "api_caller", "share")
    effective = await _effective_capabilities(
        db, agent, user, permissions, use_cache=use_cache,
    )
    tools = allowed_tool_names(effective, is_supervisor, can_manage_team)
    return AgentContext(
        agent=agent,
        user=user,
        role_code=role_code,
        permissions=permissions,
        children=children,
        effective_capabilities=effective,
        is_supervisor=is_supervisor,
        can_manage_team=can_manage_team,
        allowed_tools=tools,
    )
