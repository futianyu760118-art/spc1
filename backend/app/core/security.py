from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.basicdata.user import SysUser, SysRole

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
    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())
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


def create_share_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """为分享链接访问签发临时 JWT，包含 share 标记，有效期 24 小时"""
    to_encode = data.copy()
    to_encode["share"] = True
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


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


# 分享路径 → 允许访问的权限资源映射
_SHARE_PATH_TO_RESOURCE: dict[str, str] = {
    "/dashboard": "dashboard",
    "/orders": "orders",
    "/run-orders": "orders.run_orders",
    "/order-risk-pool": "orders.risk_pool",
    "/purchase-plan": "materials.purchase_plan",
    "/material-issues": "materials.issues",
    "/long-lead-materials": "materials.long_lead",
    "/kit-analysis": "materials.kit_analysis",
    "/supplier-risk": "materials.supplier_risk",
    "/supplier-payment": "materials.supplier_payment",
    "/issues": "exceptions",
    "/issue-log": "exceptions.issue_log",
    "/change-log": "exceptions.change_log",
    "/quality-issues": "exceptions.quality",
    "/product-samples": "exceptions.product_samples",
    "/closure-tracking": "exceptions.closure",
    "/production-overview": "production.overview",
    "/schedule-plans": "production.schedule_plans",
    "/front-process": "production.front_process",
    "/smt": "production.smt",
    "/lean": "production.lean",
    "/assembly": "production.assembly",
    "/packaging": "production.packaging",
    "/process-exceptions": "production.exceptions",
    "/meetings": "meetings",
    "/npi": "npi",
    "/import": "basicdata.import",
    "/risk-rules": "rules.risk_rules",
    "/inspection-rules": "rules.inspection",
    "/node-standards": "rules.node_standards",
    "/order-standards": "rules.order_standards",
    "/work-instructions": "rules.work_instructions",
    "/responsibility-map": "rules.responsibility",
    "/status-dict": "rules.status_dict",
    "/users": "users",
    "/audit": "audit",
    "/sync-config": "settings",
    "/basicdata/customers": "basicdata.data",
    "/basicdata/suppliers": "basicdata.data",
    "/basicdata/materials": "basicdata.data",
    "/basicdata/skus": "basicdata.data",
    "/basicdata/products": "basicdata.data",
    "/basicdata/warehouses": "basicdata.data",
    "/basicdata/processes": "basicdata.data",
    "/basicdata/organizations": "basicdata.data",
    "/basicdata/employees": "basicdata.data",
    "/basicdata/feedback": "basicdata.feedback",
    "/basicdata/files": "basicdata.files",
    "/announcements": "announcements",
}


class PermissionChecker:
    """权限校验依赖，用法: Depends(PermissionChecker("orders", "update"))
    admin角色自动通过所有权限检查
    实时从数据库查询角色权限，不依赖JWT中的旧permissions"""

    def __init__(self, resource: str, action: str):
        self.resource = resource
        self.action = action

    def _resource_candidates(self) -> list[str]:
        aliases = {
            "basicdata.import": ["masterdata.import"],
            "basicdata.data": ["masterdata.data"],
            "basicdata.feedback": ["masterdata.feedback"],
            "basicdata.files": ["masterdata.files"],
            "masterdata.import": ["basicdata.import"],
            "masterdata.data": ["basicdata.data"],
            "masterdata.feedback": ["basicdata.feedback"],
            "masterdata.files": ["basicdata.files"],
        }
        return [self.resource, *aliases.get(self.resource, [])]

    def _role_permission_additions(self, role_code: str, permissions: dict) -> dict:
        from app.core.permissions import merge_role_permission_additions

        return merge_role_permission_additions(role_code, permissions)

    async def __call__(self, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
        from app.core.token_blacklist import is_token_blacklisted

        payload = decode_access_token(token)
        role = payload.get("role", "")
        token_jti = payload.get("jti")
        token_login_version = payload.get("login_version", 0)
        is_share = payload.get("share", False)

        if token_jti and await is_token_blacklisted(token_jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="您的账号已在其他设备登录，请重新登录",
                headers={"X-Force-Logout": "true"},
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的认证凭据")

        if not is_share:
            user_result = await db.execute(select(SysUser).where(SysUser.id == int(user_id)))
            user = user_result.scalar_one_or_none()
            if not user or not user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

            db_login_version = user.login_version or 0
            if token_login_version != db_login_version:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="您的账号已在其他设备登录，请重新登录",
                    headers={"X-Force-Logout": "true"},
                )

        if role == "admin":
            return payload

        # 分享用户：只允许访问分享目标页面对应的资源，且仅限授权的操作
        if is_share:
            share_target_path = payload.get("share_target_path", "")
            share_permissions = payload.get("share_permissions", ["read"])
            allowed_resource = _SHARE_PATH_TO_RESOURCE.get(share_target_path)
            # 动态路由前缀匹配
            if not allowed_resource and "/:" in share_target_path:
                prefix = share_target_path.split("/:")[0]
                allowed_resource = _SHARE_PATH_TO_RESOURCE.get(prefix)
            if allowed_resource:
                # 检查请求的资源是否属于分享目标页面
                if self.resource == allowed_resource or self.resource.split(".")[0] == allowed_resource.split(".")[0]:
                    # 检查请求的操作是否在分享权限中
                    if self.action in share_permissions:
                        return payload
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="分享访问仅限指定页面和授权操作，无权执行此操作",
            )

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
        permissions = self._role_permission_additions(role, permissions)
        for resource in self._resource_candidates():
            allowed_actions = permissions.get(resource, [])
            if self.action in allowed_actions:
                return payload
        for resource in self._resource_candidates():
            if "." not in resource:
                continue
            parent = resource.split(".")[0]
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
