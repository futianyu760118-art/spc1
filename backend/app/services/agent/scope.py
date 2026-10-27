"""智能体数据范围解析与 SQL 过滤条件。

范围口径：本人 + 有效组织。有效组织 = 基础组织（sys_user_org_scope 或员工主组织）
∪ 额外组织（custom 模式；子智能体还会与主管有效组织求交）。组织/员工映射缺失时
宁可少给不越权，任何异常都按空范围处理并记录日志。
"""

import logging
from dataclasses import dataclass, field
from typing import Iterable, Optional, Set

from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent.agent import Agent
from app.models.basicdata.employee import Employee
from app.models.basicdata.organization import Organization
from app.models.basicdata.user import SysUser
from app.models.basicdata.user_org_scope import UserOrgScope
from app.models.exception.quality_issue import QualityIssue
from app.models.order.sale_order import SaleOrder
from app.services.agent import cache
from app.services.basicdata.org_scope_service import get_sub_org_ids

logger = logging.getLogger(__name__)


@dataclass
class ScopeContext:
    user_id: int
    username: str
    agent_id: int
    org_ids: Set[int] = field(default_factory=set)
    org_names: Set[str] = field(default_factory=set)
    member_user_ids: Set[int] = field(default_factory=set)
    member_usernames: Set[str] = field(default_factory=set)
    member_names: Set[str] = field(default_factory=set)
    include_self_owned: bool = True

    def order_condition(self):
        """销售订单：负责人 username 或部门组织名；本人数据始终可见。"""
        conds = []
        if self.member_usernames:
            conds.append(SaleOrder.owner.in_(sorted(self.member_usernames)))
        if self.org_names:
            conds.append(SaleOrder.department.in_(sorted(self.org_names)))
        return or_(*conds) if conds else false()

    def visible_order_no_select(self):
        return select(SaleOrder.order_no).where(self.order_condition()).distinct()

    def quality_condition(self):
        """品质异常：订单可见、负责人姓名、提出/责任部门组织名。"""
        conds = [
            QualityIssue.order_no.in_(self.visible_order_no_select()),
        ]
        if self.member_names:
            conds.append(QualityIssue.responsible_person.in_(sorted(self.member_names)))
        if self.org_names:
            conds.append(QualityIssue.submit_dept.in_(sorted(self.org_names)))
            conds.append(QualityIssue.responsible_dept.in_(sorted(self.org_names)))
        return or_(*conds)

    def summary(self) -> str:
        if not self.org_ids and not self.include_self_owned:
            return "无可见数据范围"
        parts = ["本人数据"]
        if self.org_names:
            names = "、".join(sorted(self.org_names)[:8])
            parts.append(f"组织范围：{names}{' 等' if len(self.org_names) > 8 else ''}")
        return "；".join(parts)


async def _expand_org_ids(db: AsyncSession, org_ids: Iterable[int], include_sub: bool) -> Set[int]:
    result: Set[int] = set()
    for org_id in org_ids:
        if org_id is None:
            continue
        if include_sub:
            result |= await get_sub_org_ids(db, int(org_id))
        else:
            result.add(int(org_id))
    return result


async def resolve_employee_main_org(db: AsyncSession, user: SysUser) -> Optional[Organization]:
    """员工主组织：emp_code → scm_employee.org_id（OA org id）→ 内部组织行。"""
    if not user.emp_code:
        return None
    emp = (await db.execute(
        select(Employee).where(Employee.emp_code == user.emp_code)
    )).scalars().first()
    if not emp or emp.org_id is None:
        return None
    return (await db.execute(
        select(Organization).where(Organization.oa_org_id == str(emp.org_id))
    )).scalars().first()


async def resolve_base_org_ids(db: AsyncSession, user: SysUser) -> Set[int]:
    """基础组织范围：显式组织范围优先；为空回退员工主组织（负责人含子树）。"""
    try:
        scopes = (await db.execute(
            select(UserOrgScope).where(UserOrgScope.user_id == user.id)
        )).scalars().all()
        if scopes:
            result: Set[int] = set()
            for scope in scopes:
                result |= await _expand_org_ids(db, [scope.org_id], bool(scope.include_sub))
            return result

        org = await resolve_employee_main_org(db, user)
        if org is None:
            return set()
        emp = (await db.execute(
            select(Employee).where(Employee.emp_code == user.emp_code)
        )).scalars().first()
        if emp and org.leader_id == emp.id:
            return await get_sub_org_ids(db, org.id)
        return {org.id}
    except Exception as exc:
        logger.warning("[agent-scope] 解析基础组织范围失败 user=%s: %s", user.id, exc)
        return set()


async def resolve_effective_org_ids(
    db: AsyncSession,
    agent: Agent,
    user: SysUser,
    *,
    use_cache: bool = True,
) -> Set[int]:
    """有效组织范围；P1 custom 额外组织由管理员配置，不与上级范围求交。"""
    cache_key = f"agent:{agent.id}:v{agent.config_version}:org"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return set(cached)

    base = await resolve_base_org_ids(db, user)
    policy = agent.capability_policy or {}
    data_scope = policy.get("data_scope") or {}
    mode = data_scope.get("mode") or "org"
    if mode == "self":
        result = set()
    elif mode == "custom":
        extra = await _expand_org_ids(
            db, data_scope.get("org_ids") or [], bool(data_scope.get("include_sub", True))
        )
        result = base | extra
    else:
        result = base

    if use_cache:
        cache.set(cache_key, result)
    return result


async def build_scope_context(
    db: AsyncSession,
    agent: Agent,
    user: SysUser,
    *,
    use_cache: bool = True,
) -> ScopeContext:
    """构造范围上下文（组织名、成员用户名/姓名/用户ID）。"""
    cache_key = f"agent:{agent.id}:v{agent.config_version}:scope"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    org_ids = await resolve_effective_org_ids(db, agent, user, use_cache=use_cache)
    org_rows = []
    if org_ids:
        org_rows = (await db.execute(
            select(Organization.id, Organization.org_name, Organization.oa_org_id)
            .where(Organization.id.in_(sorted(org_ids)))
        )).all()
    org_names = {r[1] for r in org_rows if r[1]}
    oa_ids = {str(r[2]) for r in org_rows if r[2]}

    member_rows = []
    if oa_ids:
        member_rows = (await db.execute(
            select(Employee.id, Employee.emp_name, Employee.emp_code)
            .where(Employee.org_id.in_(sorted(int(x) for x in oa_ids if x.isdigit())))
        )).all()
    emp_codes = {r[2] for r in member_rows if r[2]}
    member_usernames: Set[str] = {user.username} if user.username else set()
    member_user_ids: Set[int] = {int(user.id)}
    mapped_emp_codes: Set[str] = set()
    mapped_employee_ids: Set[int] = set()
    if emp_codes:
        user_rows = (await db.execute(
            select(SysUser.id, SysUser.username, SysUser.emp_code, SysUser.scm_employee_id)
            .where(
                or_(
                    SysUser.emp_code.in_(sorted(emp_codes)),
                    SysUser.scm_employee_id.in_([r[0] for r in member_rows if r[0]]),
                )
            )
        )).all()
        for row in user_rows:
            if row[1]:
                member_usernames.add(row[1])
            member_user_ids.add(int(row[0]))
            if row[2]:
                mapped_emp_codes.add(row[2])
            if row[3]:
                mapped_employee_ids.add(int(row[3]))
    # 只把已映射到 sys_user 的员工姓名用于品质域名称匹配；映射缺失不贡献成员。
    member_names = {
        r[1] for r in member_rows
        if r[1] and (r[2] in mapped_emp_codes or int(r[0]) in mapped_employee_ids)
    }

    context = ScopeContext(
        user_id=int(user.id),
        username=user.username or "",
        agent_id=int(agent.id),
        org_ids=org_ids,
        org_names=org_names,
        member_user_ids=member_user_ids,
        member_usernames=member_usernames,
        member_names=member_names,
        include_self_owned=True,
    )
    if use_cache:
        cache.set(cache_key, context)
    return context
