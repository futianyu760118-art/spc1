"""Tool: 查询用户"""

from typing import Any, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.user import SysUser, SysRole
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "搜索关键词，可匹配用户名、显示名称、员工工号",
        },
        "username": {
            "type": "string",
            "description": "用户名",
        },
        "emp_code": {
            "type": "string",
            "description": "员工工号",
        },
        "is_active": {
            "type": "boolean",
            "description": "是否激活",
        },
        "limit": {
            "type": "integer",
            "description": "返回结果数量限制（默认100，最大500）",
        },
    },
}


@register_tool(
    name="search_users",
    description="查询系统用户信息，包括用户名、显示名称、员工工号、角色、激活状态等。支持按关键词、用户名、员工工号、激活状态等条件查询。",
    parameters=PARAMETERS,
    display_name="用户查询",
)
async def search_users(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    keyword = params.get("keyword")
    username = params.get("username")
    emp_code = params.get("emp_code")
    is_active = params.get("is_active")
    limit = params.get("limit")

    items = []
    total = 0

    # 构建查询
    query = select(SysUser)
    count_query = select(func.count(SysUser.id))
    filters = []

    if keyword:
        like = f"%{keyword}%"
        filters.append(SysUser.username.ilike(like) | SysUser.display_name.ilike(like) | SysUser.emp_code.ilike(like))

    if username:
        filters.append(SysUser.username == username)

    if emp_code:
        filters.append(SysUser.emp_code == emp_code)

    if is_active is not None:
        filters.append(SysUser.is_active == is_active)

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    if limit:
        query = query.limit(limit)
    query = query.order_by(SysUser.created_at.desc())
    result = await db.execute(query)
    users = result.scalars().all()

    # 获取角色信息
    role_ids = {u.role_id for u in users if u.role_id}
    roles_map = {}
    if role_ids:
        role_query = select(SysRole).where(SysRole.id.in_(role_ids))
        role_result = await db.execute(role_query)
        roles = role_result.scalars().all()
        roles_map = {r.id: r for r in roles}

    for u in users:
        role = roles_map.get(u.role_id)
        items.append({
            "type": "user",
            "title": f"{u.display_name or u.username}",
            "subtitle": f"用户名: {u.username} | 工号: {u.emp_code or '无'} | 角色: {role.role_name if role else '无'}",
            "url": "/basicdata/users",
            "tags": ["激活" if u.is_active else "未激活"],
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "emp_code": u.emp_code,
            "role_id": u.role_id,
            "role_name": role.role_name if role else None,
            "role_code": role.role_code if role else None,
            "is_active": u.is_active,
            "last_login_time": u.last_login_time.isoformat() if u.last_login_time else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return {
        "items": items,
        "total": total,
    }
