from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import oauth2_scheme, decode_access_token
from app.models.masterdata.user import SysUser, SysRole


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    username = payload.get("username")
    role = payload.get("role")
    if not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
        )
    # 实时查库获取最新权限
    result = await db.execute(
        select(SysRole.permissions)
        .join(SysUser, SysUser.role_id == SysRole.id)
        .where(SysUser.id == int(user_id))
    )
    row = result.one_or_none()
    permissions = row[0] if row and row[0] else {}
    if not isinstance(permissions, dict):
        permissions = {}
    return {"user_id": int(user_id), "username": username, "role": role, "permissions": permissions}
