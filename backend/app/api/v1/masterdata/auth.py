from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.dependencies import get_current_user
from app.core.audit import log_audit
from app.models.masterdata.user import SysUser, SysRole
from app.schemas.masterdata.schemas import TokenResponse, UserInfo
from app.schemas.common import ResponseModel

router = APIRouter()


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", response_model=ResponseModel[TokenResponse])
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SysUser).where(SysUser.username == form.username, SysUser.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    role_result = await db.execute(select(SysRole).where(SysRole.id == user.role_id))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="用户角色配置异常，请联系管理员")

    token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": role.role_code, "permissions": role.permissions or {}}
    )
    return ResponseModel(data=TokenResponse(access_token=token))


@router.get("/me", response_model=ResponseModel[UserInfo])
async def get_me(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SysUser, SysRole)
        .join(SysRole, SysUser.role_id == SysRole.id)
        .where(SysUser.id == current_user["user_id"])
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    user, role = row
    return ResponseModel(data=UserInfo(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role_code=role.role_code,
        role_name=role.role_name,
        permissions=role.permissions or {},
    ))


@router.put("/change-password", response_model=ResponseModel[dict])
async def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysUser).where(SysUser.id == current_user["user_id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not verify_password(body.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="原密码错误")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")

    if body.old_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")

    user.hashed_password = get_password_hash(body.new_password)
    await log_audit(db, "sys_user", user.id, "update", field_name="password", operator=current_user["username"])
    await db.commit()
    return ResponseModel(data={"id": user.id, "message": "密码修改成功"})
