from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import oauth2_scheme, decode_access_token
from app.core.token_blacklist import is_token_blacklisted
from app.core.permissions import merge_role_permission_additions
from app.models.basicdata.user import SysUser, SysRole


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    payload = decode_access_token(token)
    is_share = payload.get("share", False)

    # 分享 token：跳过 login_version 校验和权限检查
    if is_share:
        user_id = payload.get("sub")
        share_target_path = payload.get("share_target_path", "")
        return {
            "user_id": int(user_id) if user_id else 0,
            "username": "share_user",
            "role": "share",
            "permissions": {},
            "is_share": True,
            "share_target_path": share_target_path,
        }

    # 正常用户认证流程
    user_id = payload.get("sub")
    username = payload.get("username")
    role = payload.get("role")
    token_login_version = payload.get("login_version", 0)
    token_jti = payload.get("jti")

    if not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
        )

    if token_jti and await is_token_blacklisted(token_jti):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="您的账号已在其他设备登录，请重新登录",
            headers={"X-Force-Logout": "true"},
        )

    result = await db.execute(select(SysUser).where(SysUser.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
        )

    db_login_version = user.login_version or 0
    if token_login_version != db_login_version:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="您的账号已在其他设备登录，请重新登录",
            headers={"X-Force-Logout": "true"},
        )

    role_result = await db.execute(
        select(SysRole.role_code, SysRole.permissions)
        .join(SysUser, SysUser.role_id == SysRole.id)
        .where(SysUser.id == int(user_id))
    )
    row = role_result.one_or_none()
    role_code = row[0] if row else role
    permissions = row[1] if row and row[1] else {}
    if not isinstance(permissions, dict):
        permissions = {}
    permissions = merge_role_permission_additions(role_code, permissions)
    return {"user_id": int(user_id), "username": username, "role": role, "permissions": permissions}


async def get_current_user_or_share(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取当前用户，支持分享 token 访问。
    分享 token 的 JWT 中包含 share=True 标记，跳过权限检查和 login_version 校验。"""
    payload = decode_access_token(token)
    is_share = payload.get("share", False)

    if is_share:
        # 分享访问：跳过 login_version 校验和权限检查
        user_id = payload.get("sub")
        share_target_path = payload.get("share_target_path", "")
        return {
            "user_id": int(user_id) if user_id else 0,
            "username": "share_user",
            "role": "share",
            "permissions": {},
            "is_share": True,
            "share_target_path": share_target_path,
        }

    # 正常用户认证流程
    user_id = payload.get("sub")
    username = payload.get("username")
    role = payload.get("role")
    token_login_version = payload.get("login_version", 0)
    token_jti = payload.get("jti")

    if not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
        )

    if token_jti and await is_token_blacklisted(token_jti):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="您的账号已在其他设备登录，请重新登录",
            headers={"X-Force-Logout": "true"},
        )

    result = await db.execute(select(SysUser).where(SysUser.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
        )

    db_login_version = user.login_version or 0
    if token_login_version != db_login_version:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="您的账号已在其他设备登录，请重新登录",
            headers={"X-Force-Logout": "true"},
        )

    role_result = await db.execute(
        select(SysRole.role_code, SysRole.permissions)
        .join(SysUser, SysUser.role_id == SysRole.id)
        .where(SysUser.id == int(user_id))
    )
    row = role_result.one_or_none()
    role_code = row[0] if row else role
    permissions = row[1] if row and row[1] else {}
    if not isinstance(permissions, dict):
        permissions = {}
    permissions = merge_role_permission_additions(role_code, permissions)
    return {"user_id": int(user_id), "username": username, "role": role, "permissions": permissions}
