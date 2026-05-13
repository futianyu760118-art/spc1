from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.masterdata.user import SysUser, SysRole

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )


class RoleChecker:
    """角色校验依赖，用法: Depends(RoleChecker(["admin", "operator"]))"""

    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, token: str = Depends(oauth2_scheme)):
        payload = decode_access_token(token)
        role = payload.get("role", "")
        if role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return payload


class PermissionChecker:
    """权限校验依赖，用法: Depends(PermissionChecker("orders", "update"))
    admin角色自动通过所有权限检查
    实时从数据库查询角色权限，不依赖JWT中的旧permissions"""

    def __init__(self, resource: str, action: str):
        self.resource = resource
        self.action = action

    async def __call__(self, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
        payload = decode_access_token(token)
        role = payload.get("role", "")
        # admin 自动通过
        if role == "admin":
            return payload
        # 实时查库获取角色权限，不再依赖JWT中的旧permissions
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的认证凭据")
        result = await db.execute(
            select(SysRole.permissions)
            .join(SysUser, SysUser.role_id == SysRole.id)
            .where(SysUser.id == int(user_id))
        )
        row = result.one_or_none()
        if not row or not row[0]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户角色配置异常")
        permissions = row[0]
        if not isinstance(permissions, dict):
            permissions = {}
        allowed_actions = permissions.get(self.resource, [])
        if self.action in allowed_actions:
            return payload
        # Fallback: check parent resource (e.g. 'orders.list' → 'orders')
        if "." in self.resource:
            parent = self.resource.split(".")[0]
            parent_actions = permissions.get(parent, [])
            if self.action in parent_actions:
                return payload
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"缺少 {self.resource}.{self.action} 权限",
        )


if __name__ == "__main__":
    """测试密码生成"""
    password = "admin123"
    hashed = get_password_hash(password)
    print(f"原始密码: {password}")
    print(f"哈希密码: {hashed}")
    
    # 验证密码
    is_valid = verify_password(password, hashed)
    print(f"密码是否有效: {is_valid}")
