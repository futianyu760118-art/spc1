"""用户管理 API — 仅管理员可操作"""

from typing import Optional, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker, get_password_hash
from app.core.audit import log_audit
from app.models.masterdata.user import SysUser, SysRole
from app.schemas.common import ResponseModel

router = APIRouter()


# ---------- Schemas ----------
class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    password: str
    role_id: int
    is_active: bool = True


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None


class PasswordReset(BaseModel):
    new_password: str


class RoleCreate(BaseModel):
    role_code: str
    role_name: str
    permissions: Dict[str, List[str]] = {}


class RoleUpdate(BaseModel):
    role_name: Optional[str] = None
    permissions: Optional[Dict[str, List[str]]] = None


class BatchGrantBody(BaseModel):
    role_ids: List[int]
    permissions: Dict[str, List[str]]   # 例: {"orders.list": ["read","update"]}
    mode: str = "grant"                  # grant=并集追加; revoke=移除指定 actions; replace=用本次 actions 覆盖这些 key


# ---------- 用户列表 ----------
@router.get("", response_model=ResponseModel[list])
async def list_users(
    current_user: dict = Depends(PermissionChecker("users", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SysUser, SysRole)
        .join(SysRole, SysUser.role_id == SysRole.id)
        .order_by(SysUser.id)
    )
    rows = result.all()
    return ResponseModel(data=[
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role_id": user.role_id,
            "role_code": role.role_code,
            "role_name": role.role_name,
            "is_active": user.is_active,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else None,
            "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M") if user.updated_at else None,
        }
        for user, role in rows
    ])


# ---------- 角色列表 ----------
@router.get("/roles", response_model=ResponseModel[list])
async def list_roles(
    current_user: dict = Depends(PermissionChecker("users", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysRole).order_by(SysRole.id))
    roles = result.scalars().all()
    return ResponseModel(data=[
        {"id": r.id, "role_code": r.role_code, "role_name": r.role_name, "permissions": r.permissions or {}}
        for r in roles
    ])


# ---------- 批量授权（按权限分配给多个角色） ----------
@router.post("/roles/batch-grant", response_model=ResponseModel[dict])
async def batch_grant_permissions(
    body: BatchGrantBody,
    current_user: dict = Depends(PermissionChecker("users", "update")),
    db: AsyncSession = Depends(get_db),
):
    if not body.role_ids:
        raise HTTPException(status_code=400, detail="请选择目标角色")
    if not body.permissions:
        raise HTTPException(status_code=400, detail="请选择权限项")
    if body.mode not in ("grant", "revoke", "replace"):
        raise HTTPException(status_code=400, detail="无效的模式")

    result = await db.execute(select(SysRole).where(SysRole.id.in_(body.role_ids)))
    roles = result.scalars().all()
    if not roles:
        raise HTTPException(status_code=404, detail="未找到角色")

    affected = 0
    skipped_admin = 0
    for role in roles:
        if role.role_code == "admin":
            skipped_admin += 1
            continue
        perms: Dict[str, List[str]] = dict(role.permissions or {})
        for key, actions in body.permissions.items():
            cur = set(perms.get(key, []))
            acts = set(actions or [])
            if body.mode == "grant":
                cur |= acts
            elif body.mode == "revoke":
                cur -= acts
            else:  # replace
                cur = acts
            if cur:
                perms[key] = sorted(cur)
            else:
                perms.pop(key, None)
        role.permissions = perms
        await log_audit(
            db, "sys_role", role.id, "update",
            field_name="permissions_batch", operator=current_user["username"],
        )
        affected += 1
    await db.commit()
    return ResponseModel(data={"affected": affected, "skipped_admin": skipped_admin})


# ---------- 创建角色 ----------
@router.post("/roles", response_model=ResponseModel[dict])
async def create_role(
    body: RoleCreate,
    current_user: dict = Depends(PermissionChecker("users", "create")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(SysRole).where(SysRole.role_code == body.role_code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"角色编码 '{body.role_code}' 已存在")

    role = SysRole(role_code=body.role_code, role_name=body.role_name, permissions=body.permissions)
    db.add(role)
    await db.flush()
    await log_audit(db, "sys_role", role.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(role)
    return ResponseModel(data={"id": role.id, "role_code": role.role_code})


# ---------- 更新角色 ----------
@router.put("/roles/{role_id}", response_model=ResponseModel[dict])
async def update_role(
    role_id: int,
    body: RoleUpdate,
    current_user: dict = Depends(PermissionChecker("users", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysRole).where(SysRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if body.role_name is not None:
        role.role_name = body.role_name
    if body.permissions is not None:
        role.permissions = body.permissions

    await log_audit(db, "sys_role", role.id, "update", operator=current_user["username"])
    await db.commit()
    return ResponseModel(data={"id": role.id, "role_code": role.role_code})


# ---------- 删除角色 ----------
@router.delete("/roles/{role_id}", response_model=ResponseModel[dict])
async def delete_role(
    role_id: int,
    current_user: dict = Depends(PermissionChecker("users", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysRole).where(SysRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if role.role_code == "admin":
        raise HTTPException(status_code=400, detail="不能删除系统管理员角色")

    user_count = await db.execute(
        select(func.count()).select_from(SysUser).where(SysUser.role_id == role_id)
    )
    if user_count.scalar() > 0:
        raise HTTPException(status_code=400, detail=f"该角色下有 {user_count.scalar()} 个用户，请先更换用户角色后再删除")

    await log_audit(db, "sys_role", role.id, "delete", operator=current_user["username"])
    await db.delete(role)
    await db.commit()
    return ResponseModel(data={"deleted": role_id})


# ---------- 创建用户 ----------
@router.post("", response_model=ResponseModel[dict])
async def create_user(
    body: UserCreate,
    current_user: dict = Depends(PermissionChecker("users", "create")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(SysUser).where(SysUser.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"用户名 '{body.username}' 已存在")

    role = await db.execute(select(SysRole).where(SysRole.id == body.role_id))
    if not role.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="角色不存在")

    user = SysUser(
        username=body.username,
        display_name=body.display_name,
        hashed_password=get_password_hash(body.password),
        role_id=body.role_id,
        is_active=body.is_active,
    )
    db.add(user)
    await db.flush()
    await log_audit(db, "sys_user", user.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(user)
    return ResponseModel(data={"id": user.id, "username": user.username})


# ---------- 更新用户 ----------
@router.put("/{user_id}", response_model=ResponseModel[dict])
async def update_user(
    user_id: int,
    body: UserUpdate,
    current_user: dict = Depends(PermissionChecker("users", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysUser).where(SysUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role_id is not None:
        role = await db.execute(select(SysRole).where(SysRole.id == body.role_id))
        if not role.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="角色不存在")
        user.role_id = body.role_id
    if body.is_active is not None:
        user.is_active = body.is_active

    await log_audit(db, "sys_user", user.id, "update", operator=current_user["username"])
    await db.commit()
    return ResponseModel(data={"id": user.id, "username": user.username})


# ---------- 重置密码 ----------
@router.put("/{user_id}/password", response_model=ResponseModel[dict])
async def reset_password(
    user_id: int,
    body: PasswordReset,
    current_user: dict = Depends(PermissionChecker("users", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysUser).where(SysUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于6位")

    user.hashed_password = get_password_hash(body.new_password)
    await log_audit(db, "sys_user", user.id, "update", field_name="password", operator=current_user["username"])
    await db.commit()
    return ResponseModel(data={"id": user.id, "message": "密码已重置"})


# ---------- 删除用户 ----------
@router.delete("/{user_id}", response_model=ResponseModel[dict])
async def delete_user(
    user_id: int,
    current_user: dict = Depends(PermissionChecker("users", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysUser).where(SysUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.id == current_user.get("user_id"):
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")

    await log_audit(db, "sys_user", user.id, "delete", operator=current_user["username"])
    await db.delete(user)
    await db.commit()
    return ResponseModel(data={"deleted": user_id})
