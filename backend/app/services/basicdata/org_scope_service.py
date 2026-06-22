"""组织数据范围服务 — 计算用户可访问的组织ID列表"""

from typing import List, Set
from sqlalchemy import select, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.organization import Organization
from app.models.basicdata.user_org_scope import UserOrgScope


async def get_sub_org_ids(db: AsyncSession, org_id: int) -> Set[int]:
    """递归获取某个组织的所有子孙组织ID（包含自身）"""
    result: Set[int] = {org_id}
    queue = [org_id]

    while queue:
        parents = queue[:]
        queue.clear()

        stmt = select(Organization.id).where(
            Organization.parent_id.in_(parents),
            Organization.status == 1,
        )
        rows = await db.execute(stmt)
        children = [row[0] for row in rows.all()]

        for child_id in children:
            if child_id not in result:
                result.add(child_id)
                queue.append(child_id)

    return result


async def resolve_user_org_scopes(db: AsyncSession, user_id: int) -> Set[int]:
    """计算用户可访问的所有组织ID"""
    stmt = select(UserOrgScope).where(UserOrgScope.user_id == user_id)
    rows = await db.execute(stmt)
    scopes = rows.scalars().all()

    if not scopes:
        return set()

    all_org_ids: Set[int] = set()
    for scope in scopes:
        if scope.include_sub:
            sub_ids = await get_sub_org_ids(db, scope.org_id)
            all_org_ids.update(sub_ids)
        else:
            all_org_ids.add(scope.org_id)

    return all_org_ids