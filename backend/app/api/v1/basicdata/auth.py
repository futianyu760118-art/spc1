import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.dependencies import get_current_user
from app.core.audit import log_audit
from app.core.permissions import merge_role_permission_additions
from app.core.token_blacklist import add_token_to_blacklist
from app.models.basicdata.user import SysUser, SysRole
from app.models.basicdata.supplier import Supplier
from app.schemas.basicdata.schemas import TokenResponse, UserInfo
from app.schemas.common import ResponseModel

router = APIRouter()

VALID_LOGIN_TYPES = {"employee", "supplier"}


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdatePreferencesRequest(BaseModel):
    font_size_scale: str


@router.post("/login", response_model=ResponseModel[TokenResponse])
async def login(
        form: OAuth2PasswordRequestForm = Depends(),
        login_type: str = Form("employee"),
        db: AsyncSession = Depends(get_db),
):
    login_type = (login_type or "employee").strip().lower()
    if login_type not in VALID_LOGIN_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="登录类型不正确")

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

    is_supplier_account = role.role_code == "supplier"
    if login_type == "supplier" and not is_supplier_account:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号不是供应商账号，请选择内部员工登录")
    if login_type == "employee" and is_supplier_account:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号为供应商账号，请选择供应商登录")

    supplier_code = None
    if is_supplier_account:
        if not user.supplier_name:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="供应商账号未绑定供应商")
        supplier_result = await db.execute(
            select(Supplier).where(
                Supplier.supplier_name == user.supplier_name,
                Supplier.status == 1,
            )
        )
        supplier = supplier_result.scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="绑定供应商不存在或已停用")
        supplier_code = supplier.supplier_code

    old_token_jti = user.last_token_jti

    user.login_version = (user.login_version or 0) + 1
    user.last_login_time = datetime.now()
    new_jti = str(uuid.uuid4())

    permissions = merge_role_permission_additions(role.role_code, role.permissions)

    token_payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": role.role_code,
        "permissions": permissions,
        "login_type": login_type,
        "supplier_name": user.supplier_name if is_supplier_account else None,
        "login_version": user.login_version,
        "jti": new_jti,
    }
    if supplier_code:
        token_payload["supplier_code"] = supplier_code

    token = create_access_token(
        data=token_payload
    )

    user.last_token_jti = new_jti
    await db.commit()

    if old_token_jti:
        try:
            await add_token_to_blacklist(old_token_jti)
        except Exception:
            pass

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
    supplier_code = None
    if role.role_code == "supplier" and user.supplier_name:
        supplier_result = await db.execute(
            select(Supplier.supplier_code).where(
                Supplier.supplier_name == user.supplier_name,
                Supplier.status == 1,
            )
        )
        supplier_code = supplier_result.scalar_one_or_none()

    settings = get_settings()
    if user.login_version > 0 and user.is_default_password==True:
        is_default = verify_password(settings.ERP_SYNC_DEFAULT_PASSWORD, user.hashed_password)
    else:
        is_default = user.is_default_password

    return ResponseModel(data=UserInfo(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role_code=role.role_code,
        role_name=role.role_name,
        permissions=merge_role_permission_additions(role.role_code, role.permissions),
        supplier_name=user.supplier_name,
        supplier_code=supplier_code,
        font_size_scale=user.font_size_scale,
        is_default_password=is_default,
        login_version=user.login_version,
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
    user.is_default_password = False
    await log_audit(db, "sys_user", user.id, "update", field_name="password", operator=current_user["username"])
    await db.commit()
    return ResponseModel(data={"id": user.id, "message": "密码修改成功"})


@router.put("/preferences", response_model=ResponseModel[dict])
async def update_preferences(
        body: UpdatePreferencesRequest,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysUser).where(SysUser.id == current_user["user_id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.font_size_scale = body.font_size_scale
    await db.commit()
    return ResponseModel(data={"id": user.id, "message": "偏好设置已更新"})
