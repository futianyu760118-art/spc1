"""用户管理 API — 仅管理员可操作"""

from typing import Optional, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker, get_password_hash
from app.core.audit import log_audit
from app.core.permissions import merge_role_permission_additions
from app.models.basicdata.employee import Employee
from app.models.basicdata.position import Position
from app.models.basicdata.supplier import Supplier
from app.models.basicdata.user import SysUser, SysRole
from app.schemas.common import ResponseModel
from app.services.basicdata.position_role_service import resolve_employee_role_by_code
from app.services.common.export_service import ExportColumn, GenericExportService

router = APIRouter()

USER_EXPORT_COLUMNS = [
    ExportColumn("username", "用户名", 18),
    ExportColumn("display_name", "显示名称", 18),
    ExportColumn("emp_code", "员工工号", 16),
    ExportColumn("emp_name", "员工姓名", 16),
    ExportColumn("position_name", "岗位", 18),
    ExportColumn("role_code", "角色编码", 16),
    ExportColumn("role_name", "角色名称", 18),
    ExportColumn("supplier_name", "绑定供应商", 24),
    ExportColumn("is_active", "状态", 10),
    ExportColumn("last_login_time", "最后登录", 18),
    ExportColumn("created_at", "创建时间", 18),
    ExportColumn("updated_at", "更新时间", 18),
]


# ---------- Schemas ----------
class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    password: str
    role_id: Optional[int] = None
    emp_code: Optional[str] = None
    supplier_name: Optional[str] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role_id: Optional[int] = None
    emp_code: Optional[str] = None
    supplier_name: Optional[str] = None
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


async def _resolve_role(role_id: int, db: AsyncSession) -> SysRole:
    result = await db.execute(select(SysRole).where(SysRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=400, detail="角色不存在")
    return role


async def _resolve_user_role(
    role_id: Optional[int],
    emp_code: Optional[str],
    db: AsyncSession,
) -> tuple[SysRole, Optional[Employee], Optional[Position]]:
    clean_emp_code = (emp_code or "").strip()
    if clean_emp_code:
        employee, position, role = await resolve_employee_role_by_code(db, clean_emp_code)
        if not employee:
            raise HTTPException(status_code=400, detail="关联员工不存在")
        if role:
            return role, employee, position

    if role_id is None:
        raise HTTPException(status_code=400, detail="请选择角色或关联有岗位的员工")

    return await _resolve_role(role_id, db), employee if clean_emp_code else None, position if clean_emp_code else None


async def _validate_supplier_binding(role: SysRole, supplier_name: Optional[str], db: AsyncSession) -> Optional[str]:
    if role.role_code != "supplier":
        return None

    name = supplier_name or ""
    if not name:
        raise HTTPException(status_code=400, detail="供应商账号必须绑定供应商")

    result = await db.execute(
        select(Supplier).where(
            Supplier.supplier_name == name,
            Supplier.status == 1,
        )
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=400, detail="绑定供应商不存在或已停用")
    return supplier.supplier_name


# ---------- 用户列表 ----------
@router.get("", response_model=ResponseModel[list])
async def list_users(
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    role_code: Optional[str] = None,
    is_active: Optional[bool] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(PermissionChecker("users", "read")),
    db: AsyncSession = Depends(get_db),
):
    SORTABLE = {
        'username': SysUser.username,
        'display_name': SysUser.display_name,
        'emp_code': SysUser.emp_code,
        'role_code': SysRole.role_code,
        'is_active': SysUser.is_active,
        'last_login_time': SysUser.last_login_time,
        'created_at': SysUser.created_at,
    }

    query = (
        select(SysUser, SysRole, Employee, Position)
        .join(SysRole, SysUser.role_id == SysRole.id)
        .outerjoin(Employee, SysUser.emp_code == Employee.emp_code)
        .outerjoin(Position, Employee.position_id == Position.id)
    )

    if role_code:
        codes = [c.strip() for c in role_code.split(",") if c.strip()]
        if codes:
            query = query.where(SysRole.role_code.in_(codes))
    if is_active is not None:
        query = query.where(SysUser.is_active == is_active)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            (SysUser.username.ilike(like))
            | (SysUser.display_name.ilike(like))
            | (SysUser.emp_code.ilike(like))
            | (Employee.emp_name.ilike(like))
        )

    # 排序
    order_clauses = []
    if sort_by and sort_by in SORTABLE:
        col = SORTABLE[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    if not order_clauses:
        order_clauses = [SysUser.id.asc()]

    result = await db.execute(query.order_by(*order_clauses))
    rows = result.all()
    return ResponseModel(data=[
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "emp_code": user.emp_code,
            "emp_name": employee.emp_name if employee else None,
            "position_id": employee.position_id if employee else None,
            "position_name": position.position_name if position else (employee.position if employee else None),
            "role_id": user.role_id,
            "role_code": role.role_code,
            "role_name": role.role_name,
            "supplier_name": user.supplier_name,
            "is_active": user.is_active,
            "last_login_time": user.last_login_time.strftime("%Y-%m-%d %H:%M") if user.last_login_time else None,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else None,
            "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M") if user.updated_at else None,
        }
        for user, role, employee, position in rows
    ])


@router.get("/export")
async def export_users(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    columns: Optional[str] = Query(None),
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    role_code: Optional[str] = None,
    is_active: Optional[bool] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(PermissionChecker("users", "read")),
    db: AsyncSession = Depends(get_db),
):
    SORTABLE = {
        'username': SysUser.username,
        'display_name': SysUser.display_name,
        'emp_code': SysUser.emp_code,
        'role_code': SysRole.role_code,
        'is_active': SysUser.is_active,
        'last_login_time': SysUser.last_login_time,
        'created_at': SysUser.created_at,
    }

    query = (
        select(SysUser, SysRole, Employee, Position)
        .join(SysRole, SysUser.role_id == SysRole.id)
        .outerjoin(Employee, SysUser.emp_code == Employee.emp_code)
        .outerjoin(Position, Employee.position_id == Position.id)
    )

    if role_code:
        codes = [c.strip() for c in role_code.split(",") if c.strip()]
        if codes:
            query = query.where(SysRole.role_code.in_(codes))
    if is_active is not None:
        query = query.where(SysUser.is_active == is_active)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            (SysUser.username.ilike(like))
            | (SysUser.display_name.ilike(like))
            | (SysUser.emp_code.ilike(like))
            | (Employee.emp_name.ilike(like))
        )

    order_clauses = []
    if sort_by and sort_by in SORTABLE:
        col = SORTABLE[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    if not order_clauses:
        order_clauses = [SysUser.id.asc()]

    result = await db.execute(query.order_by(*order_clauses))
    rows = result.all()

    selected_keys = [c.strip() for c in columns.split(",") if c.strip()] if columns else []
    allowed = {col.key for col in USER_EXPORT_COLUMNS}
    selected_columns = [col for col in USER_EXPORT_COLUMNS if not selected_keys or col.key in selected_keys]
    if selected_keys and not selected_columns:
        raise HTTPException(status_code=400, detail="请选择至少一个有效导出字段")
    invalid_columns = [key for key in selected_keys if key not in allowed]
    if invalid_columns:
        raise HTTPException(status_code=400, detail=f"无效导出字段: {', '.join(invalid_columns)}")

    export_rows = []
    for user, role, employee, position in rows:
        export_rows.append({
            "username": user.username,
            "display_name": user.display_name or "",
            "emp_code": user.emp_code or "",
            "emp_name": employee.emp_name if employee else "",
            "position_name": position.position_name if position else (employee.position if employee else ""),
            "role_code": role.role_code,
            "role_name": role.role_name,
            "supplier_name": user.supplier_name or "",
            "is_active": "启用" if user.is_active else "停用",
            "last_login_time": user.last_login_time.strftime("%Y-%m-%d %H:%M") if user.last_login_time else "",
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else "",
            "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M") if user.updated_at else "",
        })

    svc = GenericExportService(selected_columns, export_rows, sheet_name="用户管理")
    if format == "csv":
        output = svc.to_csv()
        return StreamingResponse(
            output,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=users.csv"},
        )

    output = svc.to_xlsx()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=users.xlsx"},
    )


# ---------- 角色列表 ----------
@router.get("/roles", response_model=ResponseModel[list])
async def list_roles(
    current_user: dict = Depends(PermissionChecker("users", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysRole).order_by(SysRole.id))
    roles = result.scalars().all()
    return ResponseModel(data=[
        {
            "id": r.id,
            "role_code": r.role_code,
            "role_name": r.role_name,
            "permissions": merge_role_permission_additions(r.role_code, r.permissions),
        }
        for r in roles
    ])


@router.get("/employee-options", response_model=ResponseModel[list])
async def list_employee_options(
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("users", "read")),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Employee, Position, SysRole)
        .outerjoin(Position, Employee.position_id == Position.id)
        .outerjoin(SysRole, Position.role_id == SysRole.id)
    )
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            or_(
                Employee.emp_code.ilike(like),
                Employee.emp_name.ilike(like),
                Employee.login_id.ilike(like),
                Position.position_name.ilike(like),
            )
        )

    result = await db.execute(query.order_by(Employee.emp_code.asc()).limit(200))
    return ResponseModel(data=[
        {
            "emp_code": employee.emp_code,
            "emp_name": employee.emp_name,
            "login_id": employee.login_id,
            "position_id": employee.position_id,
            "position_name": position.position_name if position else employee.position,
            "role_id": role.id if role else None,
            "role_code": role.role_code if role else None,
            "role_name": role.role_name if role else None,
            "status": employee.status,
        }
        for employee, position, role in result.all()
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

    role, employee, _ = await _resolve_user_role(body.role_id, body.emp_code, db)
    supplier_name = await _validate_supplier_binding(role, body.supplier_name, db)

    user = SysUser(
        username=body.username,
        display_name=body.display_name or (employee.emp_name if employee else None),
        hashed_password=get_password_hash(body.password),
        role_id=role.id,
        supplier_name=supplier_name,
        emp_code=employee.emp_code if employee else None,
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
    if body.role_id is not None or body.emp_code is not None:
        role, employee, _ = await _resolve_user_role(
            body.role_id if body.role_id is not None else user.role_id,
            body.emp_code if body.emp_code is not None else user.emp_code,
            db,
        )
        user.supplier_name = await _validate_supplier_binding(role, body.supplier_name, db)
        user.role_id = role.id
        user.emp_code = employee.emp_code if employee else None
        if employee and body.display_name is None:
            user.display_name = employee.emp_name
    elif body.supplier_name is not None:
        role = await _resolve_role(user.role_id, db)
        user.supplier_name = await _validate_supplier_binding(role, body.supplier_name, db)
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
