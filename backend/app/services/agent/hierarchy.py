"""智能体层级治理：主管绑定叶子、管理员改挂/解绑/锁定。"""

import logging
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent.agent import Agent, AgentHierarchyLog
from app.models.basicdata.employee import Employee
from app.models.basicdata.user import SysRole, SysUser
from app.services.agent import cache
from app.services.agent.context import AgentContext, get_or_create_agent
from app.services.agent.errors import AgentError
from app.services.agent.notify import notify_user

logger = logging.getLogger(__name__)


class HierarchyError(AgentError):
    pass


async def list_candidates(db: AsyncSession, keyword: str = "", limit: int = 30) -> List[dict]:
    """主管可绑定的候选用户：内部、启用、当前为叶子（无上级且无子智能体）。"""
    stmt = (
        select(SysUser, SysRole.role_code, Agent, Employee.emp_name)
        .join(SysRole, SysRole.id == SysUser.role_id)
        .outerjoin(Agent, Agent.user_id == SysUser.id)
        .outerjoin(Employee, Employee.emp_code == SysUser.emp_code)
        .where(
            SysUser.is_active == True,  # noqa: E712
            SysRole.role_code.notin_(("supplier", "api_caller", "share")),
        )
    )
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(
            SysUser.username.ilike(like),
            SysUser.display_name.ilike(like),
            Employee.emp_name.ilike(like),
        ))
    rows = (await db.execute(stmt.order_by(SysUser.id.asc()).limit(limit * 3))).all()
    items = []
    for user, role_code, agent, employee_name in rows:
        has_parent = bool(agent and agent.parent_agent_id)
        has_child = False
        if agent:
            has_child = bool((await db.execute(
                select(Agent.id).where(Agent.parent_agent_id == agent.id).limit(1)
            )).first())
        items.append({
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "employee_name": employee_name,
            "role_code": role_code,
            "status": "active" if user.is_active else "disabled",
            "agent_id": agent.id if agent else None,
            "bindable": not has_parent and not has_child,
        })
        if len(items) >= limit:
            break
    return items


async def _ensure_not_ancestor(db: AsyncSession, target: Agent, candidate_parent: Agent) -> None:
    """候选上级不能是目标自身或目标后代（防环）。"""
    if candidate_parent.id == target.id:
        raise HierarchyError("不能把智能体挂到自己下面", 400)
    seen = set()
    current: Optional[Agent] = candidate_parent
    while current and current.parent_agent_id and current.id not in seen:
        seen.add(current.id)
        if current.parent_agent_id == target.id:
            raise HierarchyError("不能把智能体挂到自己的后代下面", 400)
        current = await db.get(Agent, current.parent_agent_id)
    if current and current.id == target.id:
        raise HierarchyError("不能把智能体挂到自己的后代下面", 400)


async def _is_leaf(db: AsyncSession, agent: Agent) -> bool:
    if agent.parent_agent_id:
        return False
    child = (await db.execute(
        select(Agent.id).where(Agent.parent_agent_id == agent.id).limit(1)
    )).first()
    return child is None


async def add_subordinate(db: AsyncSession, ctx: AgentContext, *, user_id: Optional[int] = None, username: str = "") -> dict:
    """主管直接绑定一个叶子智能体；目标必须无上级且无子智能体。"""
    if ctx.role_code == "supplier":
        raise HierarchyError("供应商用户不能创建团队", 403)
    if ctx.agent.status != "active":
        raise HierarchyError("当前智能体已禁用", 403)

    target_user = None
    if user_id:
        target_user = await db.get(SysUser, int(user_id))
    elif username:
        target_user = (await db.execute(
            select(SysUser).where(SysUser.username == username)
        )).scalars().first()
    if not target_user or not target_user.is_active:
        raise HierarchyError("目标用户不存在或已停用", 404)
    if target_user.id == ctx.user.id:
        raise HierarchyError("不能绑定自己", 400)
    target_role = await db.get(SysRole, target_user.role_id)
    if target_role and target_role.role_code in ("supplier", "api_caller", "share"):
        raise HierarchyError("目标用户不是内部用户", 400)

    target_agent = await get_or_create_agent(db, target_user, created_by_user_id=ctx.user.id)
    if not await _is_leaf(db, target_agent):
        raise HierarchyError("目标智能体已有上级或子智能体，仅管理员可改挂", 403)
    if await _is_ancestor(db, target_agent, ctx.agent):
        raise HierarchyError("目标智能体是当前智能体的上级", 400)

    old_parent = target_agent.parent_agent_id
    target_agent.parent_agent_id = ctx.agent.id
    db.add(AgentHierarchyLog(
        agent_id=target_agent.id,
        old_parent_id=old_parent,
        new_parent_id=ctx.agent.id,
        action="bind",
        actor_user_id=int(ctx.user.id),
        reason=f"主管 {ctx.user.username} 绑定直属成员",
    ))
    cache.invalidate_agent(target_agent.id)
    await db.flush()
    await notify_user(
        db,
        user_id=target_user.id,
        title="[智能体]你已被添加为直属成员",
        content=f"{ctx.user.display_name or ctx.user.username} 将你加入其团队，立即生效",
        notif_type="agent_hierarchy",
        ref_type="agent",
        ref_id=ctx.agent.id,
        sender_id=ctx.user.id,
        sender_name=ctx.user.display_name or ctx.user.username,
    )
    return {
        "agent_id": target_agent.id,
        "user_id": target_user.id,
        "display_name": target_agent.display_name,
        "parent_agent_id": ctx.agent.id,
    }


async def _is_ancestor(db: AsyncSession, candidate: Agent, node: Agent) -> bool:
    current: Optional[Agent] = node
    seen = set()
    while current and current.id not in seen:
        if current.id == candidate.id:
            return True
        seen.add(current.id)
        current = await db.get(Agent, current.parent_agent_id) if current.parent_agent_id else None
    return False


async def admin_change_hierarchy(
    db: AsyncSession,
    *,
    actor: SysUser,
    target_agent_id: int,
    action: str,
    new_parent_id: Optional[int] = None,
    reason: str = "",
) -> dict:
    """管理员改挂 / 解绑 / 锁定 / 解锁。"""
    target = await db.get(Agent, int(target_agent_id))
    if not target:
        raise HierarchyError("智能体不存在", 404)

    if action == "lock":
        target.status = "disabled"
    elif action == "unlock":
        target.status = "active"
    elif action in ("reparent", "unbind"):
        if action == "unbind":
            new_parent = None
        else:
            new_parent = await db.get(Agent, int(new_parent_id)) if new_parent_id else None
            if not new_parent:
                raise HierarchyError("目标上级智能体不存在", 404)
            if new_parent.status != "active":
                raise HierarchyError("目标上级智能体已禁用", 400)
            await _ensure_not_ancestor(db, target, new_parent)
        old_parent = target.parent_agent_id
        target.parent_agent_id = new_parent.id if new_parent else None
        db.add(AgentHierarchyLog(
            agent_id=target.id,
            old_parent_id=old_parent,
            new_parent_id=target.parent_agent_id,
            action=action,
            actor_user_id=int(actor.id),
            reason=(reason or "")[:2000] or None,
        ))
        cache.invalidate_agent(target.id)
    else:
        raise HierarchyError("不支持的层级动作", 400)

    if action in ("lock", "unlock"):
        db.add(AgentHierarchyLog(
            agent_id=target.id,
            old_parent_id=target.parent_agent_id,
            new_parent_id=target.parent_agent_id,
            action=action,
            actor_user_id=int(actor.id),
            reason=(reason or "")[:2000] or None,
        ))
        cache.invalidate_agent(target.id)

    await db.flush()
    target_user = await db.get(SysUser, target.user_id)
    if target_user:
        await notify_user(
            db,
            user_id=target_user.id,
            title="[智能体]你的团队关系已调整",
            content=f"动作：{action}；操作人：{actor.display_name or actor.username}",
            notif_type="agent_hierarchy",
            ref_type="agent",
            ref_id=target.id,
            sender_id=actor.id,
            sender_name=actor.display_name or actor.username,
        )
    return {
        "agent_id": target.id,
        "status": target.status,
        "parent_agent_id": target.parent_agent_id,
        "action": action,
    }
