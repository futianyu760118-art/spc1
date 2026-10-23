"""按权限查找活跃用户。

必须走 merge_role_permission_additions，不能用纯 SQL JSONB 查询：
代码侧 additions 可能给角色加权限而 sys_role.permissions 未落库。
"""

from typing import Callable, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import merge_role_permission_additions
from app.models.basicdata.user import SysRole, SysUser

RolePredicate = Callable[[str, Dict[str, List[str]]], bool]


async def user_ids_matching(db: AsyncSession, predicate: RolePredicate) -> List[int]:
    roles = (await db.execute(select(SysRole))).scalars().all()
    role_ids = [
        role.id
        for role in roles
        if predicate(
            role.role_code,
            merge_role_permission_additions(
                role.role_code,
                role.permissions if isinstance(role.permissions, dict) else {},
            ),
        )
    ]
    if not role_ids:
        return []
    rows = await db.execute(
        select(SysUser.id).where(
            SysUser.is_active.is_(True),
            SysUser.role_id.in_(role_ids),
        )
    )
    return [int(uid) for uid in rows.scalars().all()]


async def user_ids_with_permission(
    db: AsyncSession, resource: str, permission_action: str = "read",
    include_admin: bool = True,
) -> List[int]:
    """与 PermissionChecker 同口径：admin 直通 + 父级 fallback（basicdata/masterdata 别名未覆盖）。"""

    def _match(role_code: str, perms: Dict[str, List[str]]) -> bool:
        if include_admin and role_code == "admin":
            return True
        if permission_action in (perms.get(resource) or []):
            return True
        parts = resource.split(".")
        for index in range(len(parts) - 1, 0, -1):
            parent = ".".join(parts[:index])
            if permission_action in (perms.get(parent) or []):
                return True
        return False

    return await user_ids_matching(db, _match)
