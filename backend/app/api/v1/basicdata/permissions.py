"""权限定义 API — 提供权限树和权限列表接口"""

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.basicdata.permission import SysPermission
from app.schemas.common import ResponseModel

router = APIRouter()


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
    db: AsyncSession = Depends(get_db),
):
    """获取权限树结构，供前端动态渲染菜单和权限矩阵"""
    result = await db.execute(
        select(SysPermission)
        .where(SysPermission.is_active == True)
        .order_by(SysPermission.sort_order.asc())
    )
    permissions = result.scalars().all()
    tree = _build_tree(list(permissions))
    return ResponseModel(data=tree)


@router.get("", response_model=ResponseModel[list])
async def get_permission_list(
    db: AsyncSession = Depends(get_db),
):
    """获取权限扁平列表"""
    result = await db.execute(
        select(SysPermission)
        .where(SysPermission.is_active == True)
        .order_by(SysPermission.sort_order.asc())
    )
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
