"""权限定义 API — 提供权限树和权限列表接口，以及权限定义的运行时 CRUD"""

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.basicdata.permission import SysPermission
from app.models.basicdata.user import SysRole
from app.schemas.common import ResponseModel

router = APIRouter()


_PROTECTED_CODES = {"permissions", "roles", "users", "users.reset_password"}
_STANDARD_ACTIONS = ["create", "read", "update", "delete", "import", "handle"]


class PermissionCreate(BaseModel):
    code: str
    name: str
    module: str
    parent_code: Optional[str] = None
    actions: Optional[List[str]] = None
    route_path: Optional[str] = None
    sort_order: int = 0


class PermissionUpdate(BaseModel):
    name: Optional[str] = None
    parent_code: Optional[str] = None
    module: Optional[str] = None
    actions: Optional[List[str]] = None
    route_path: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


def _build_tree(permissions: List[SysPermission]) -> List[dict]:
    """将扁平权限列表构建为树形结构"""
    # 按 parent_code 分组
    children_map: Dict[Optional[str], List[dict]] = {}
    perm_map: Dict[str, dict] = {}

    for p in permissions:
        node = {
            "code": p.code,
            "name": p.name,
            "module": p.module,
            "parent_code": p.parent_code,
            "actions": p.actions or [],
            "route_path": p.route_path,
            "sort_order": p.sort_order,
            "is_active": p.is_active,
            "children": [],
        }
        perm_map[p.code] = node
        if p.parent_code not in children_map:
            children_map[p.parent_code] = []
        children_map[p.parent_code].append(node)

    # 将子节点挂到父节点
    for code, node in perm_map.items():
        kids = children_map.get(code, [])
        # 按 sort_order 排序
        kids.sort(key=lambda x: x["sort_order"])
        node["children"] = kids

    # 根节点 = parent_code 为 None 的节点
    roots = children_map.get(None, [])
    roots.sort(key=lambda x: x["sort_order"])
    return roots


@router.get("/tree", response_model=ResponseModel[list])
async def get_permission_tree(
    include_inactive: bool = Query(False, description="包含停用的权限节点（需 permissions.read）"),
    db: AsyncSession = Depends(get_db),
):
    """获取权限树结构，供前端动态渲染菜单和权限矩阵"""
    stmt = select(SysPermission).order_by(SysPermission.sort_order.asc())
    if not include_inactive:
        stmt = stmt.where(SysPermission.is_active == True)
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    tree = _build_tree(list(permissions))
    return ResponseModel(data=tree)


@router.get("", response_model=ResponseModel[list])
async def get_permission_list(
    include_inactive: bool = Query(False, description="包含停用的权限节点"),
    db: AsyncSession = Depends(get_db),
):
    """获取权限扁平列表"""
    stmt = select(SysPermission).order_by(SysPermission.sort_order.asc())
    if not include_inactive:
        stmt = stmt.where(SysPermission.is_active == True)
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    return ResponseModel(data=[
        {
            "code": p.code,
            "name": p.name,
            "module": p.module,
            "parent_code": p.parent_code,
            "actions": p.actions or [],
            "route_path": p.route_path,
            "sort_order": p.sort_order,
            "is_active": p.is_active,
        }
        for p in permissions
    ])


@router.get("/route-map", response_model=ResponseModel[dict])
async def get_route_permission_map(
    db: AsyncSession = Depends(get_db),
):
    """获取 route_path → permission code 映射，供前端和分享功能使用"""
    result = await db.execute(
        select(SysPermission.code, SysPermission.route_path)
        .where(SysPermission.route_path.isnot(None), SysPermission.is_active == True)
    )
    route_map = {row[1]: row[0] for row in result.all() if row[1]}
    return ResponseModel(data=route_map)


@router.post("", response_model=ResponseModel[dict])
async def create_permission(
    body: PermissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("permissions", "create")),
):
    """新增权限定义节点"""
    code = body.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="权限编码不能为空")
    existing = (await db.execute(select(SysPermission).where(SysPermission.code == code))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"权限编码 {code} 已存在")
    if body.parent_code:
        if body.parent_code == code:
            raise HTTPException(status_code=400, detail="父级不能是自身")
        parent = (await db.execute(select(SysPermission).where(SysPermission.code == body.parent_code))).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=400, detail=f"父级权限 {body.parent_code} 不存在")
    actions = body.actions if body.actions is not None else ["create", "read", "update", "delete"]
    perm = SysPermission(
        code=code,
        name=body.name,
        module=body.module,
        parent_code=body.parent_code,
        actions=actions,
        route_path=body.route_path,
        sort_order=body.sort_order,
        is_active=True,
    )
    db.add(perm)
    await db.flush()
    await db.commit()
    await db.refresh(perm)
    return ResponseModel(message="创建成功", data={"code": perm.code, "name": perm.name})


@router.put("/{code}", response_model=ResponseModel[dict])
async def update_permission(
    code: str,
    body: PermissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("permissions", "update")),
):
    """更新权限定义（code 不可变；受保护权限不可停用）"""
    perm = (await db.execute(select(SysPermission).where(SysPermission.code == code))).scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="权限定义不存在")
    if body.is_active is False and code in _PROTECTED_CODES:
        raise HTTPException(status_code=400, detail=f"受保护权限 {code} 不能停用")
    if body.parent_code is not None and body.parent_code != perm.parent_code:
        new_parent = body.parent_code or ""
        if new_parent == code:
            raise HTTPException(status_code=400, detail="父级不能是自身")
        if new_parent:
            # 校验新父级存在，且不是自身的后代（避免环）
            all_perms = (await db.execute(select(SysPermission))).scalars().all()
            codes_by_parent = {p.code: p.parent_code for p in all_perms}
            target = new_parent
            while target:
                if target == code:
                    raise HTTPException(status_code=400, detail="不能将权限挂到自身后代下（会形成环）")
                target = codes_by_parent.get(target)
            parent = next((p for p in all_perms if p.code == new_parent), None)
            if not parent:
                raise HTTPException(status_code=400, detail=f"父级权限 {new_parent} 不存在")
        perm.parent_code = body.parent_code
    if body.name is not None:
        perm.name = body.name
    if body.module is not None:
        perm.module = body.module
    if body.actions is not None:
        perm.actions = body.actions
    if body.route_path is not None:
        perm.route_path = body.route_path
    if body.sort_order is not None:
        perm.sort_order = body.sort_order
    if body.is_active is not None:
        perm.is_active = body.is_active
    await db.commit()
    await db.refresh(perm)
    return ResponseModel(message="更新成功", data={"code": perm.code, "name": perm.name})


@router.delete("/{code}", response_model=ResponseModel[dict])
async def delete_permission(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(PermissionChecker("permissions", "delete")),
):
    """删除权限定义（受保护权限不可删；有子节点不可删；同时清除所有角色的该权限引用）"""
    if code in _PROTECTED_CODES:
        raise HTTPException(status_code=400, detail=f"受保护权限 {code} 不能删除")
    perm = (await db.execute(select(SysPermission).where(SysPermission.code == code))).scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="权限定义不存在")
    child_count = (await db.execute(
        select(SysPermission.id).where(SysPermission.parent_code == code).limit(1)
    )).first()
    if child_count:
        raise HTTPException(status_code=400, detail="该权限下还有子节点，请先删除子节点")
    await db.delete(perm)
    # 清除所有角色 permissions 中的该 code 引用
    await db.execute(
        text(
            "UPDATE sys_role "
            "SET permissions = permissions - CAST(:code AS text) "
            "WHERE permissions ? CAST(:code AS text)"
        ),
        {"code": code},
    )
    await db.commit()
    return ResponseModel(message="删除成功", data={"code": code})
