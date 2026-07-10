"""仓储对外接口

为外部系统（如 WMS / ERP）提供仓库 / 库位 主数据查询。
基于 Warehouse（scm_warehouse）与 Location（scm_location）表。
对外只暴露精简字段集与常用筛选条件，字段集合独立于表结构变更。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.basicdata.warehouse import Warehouse
from app.models.basicdata.location import Location

from ..registry import register_external, ExternalCallContext


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════
# 仓库
# ═══════════════════════════════════════════

@register_external(
    "warehouses.list",
    "仓库列表",
    method="GET",
    path="/warehouses/list",
    description="仓库主数据列表查询，支持关键字、仓库类型、仓库属性、启用状态、增量同步",
    tags=["仓储"],
)
async def warehouses_list(ctx: ExternalCallContext) -> dict:
    """仓库列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（仓库编码 / 仓库名称 模糊匹配）
        wh_type: 仓库类型精确匹配
        wh_attribute: 仓库属性精确匹配 (10-良品 11-在检 12-不良)
        is_enabled: 是否启用 (0/1)
        updated_after: 增量同步，仅返回 updated_at >= 此时间的记录 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    wh_type = params.get("wh_type")
    wh_attribute = params.get("wh_attribute")
    is_enabled = params.get("is_enabled")
    updated_after = _parse_dt(params.get("updated_after"))

    # 默认排除已删除仓库
    query = select(Warehouse).where(Warehouse.is_deleted != 1)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Warehouse.wh_code.ilike(like_expr),
            Warehouse.wh_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if wh_type:
        query = query.where(Warehouse.wh_type == wh_type)
        count_query = select(func.count()).select_from(query.subquery())

    if wh_attribute:
        query = query.where(Warehouse.wh_attribute == wh_attribute)
        count_query = select(func.count()).select_from(query.subquery())

    if is_enabled is not None and is_enabled != "":
        query = query.where(Warehouse.is_enabled == int(is_enabled))
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(Warehouse.updated_at >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Warehouse.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "wh_id": r.wh_id,
        "parent_wh_id": r.parent_wh_id,
        "wh_code": r.wh_code,
        "wh_name": r.wh_name,
        "wh_type": r.wh_type,
        "wh_attribute": r.wh_attribute,
        "plan_area": r.plan_area,
        "is_workshop": r.is_workshop,
        "is_enabled": r.is_enabled,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ═══════════════════════════════════════════
# 库位
# ═══════════════════════════════════════════

@register_external(
    "locations.list",
    "库位列表",
    method="GET",
    path="/locations/list",
    description="库位主数据列表查询，支持关键字、父库位、明细标识、增量同步",
    tags=["仓储"],
)
async def locations_list(ctx: ExternalCallContext) -> dict:
    """库位列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（库位编码 / 库位名称 / 库位全称 模糊匹配）
        parent_id: 父库位ID精确匹配
        detail_flag: 明细标识精确匹配 (0/1)
        updated_after: 增量同步，仅返回 updated_at >= 此时间的记录 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    parent_id = params.get("parent_id")
    detail_flag = params.get("detail_flag")
    updated_after = _parse_dt(params.get("updated_after"))

    # 默认排除已删除库位
    query = select(Location).where(Location.is_deleted != 1)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Location.location_code.ilike(like_expr),
            Location.location_name.ilike(like_expr),
            Location.location_full_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if parent_id is not None and parent_id != "":
        query = query.where(Location.parent_id == int(parent_id))
        count_query = select(func.count()).select_from(query.subquery())

    if detail_flag is not None and detail_flag != "":
        query = query.where(Location.detail_flag == int(detail_flag))
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(Location.updated_at >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Location.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "location_id": r.location_id,
        "location_group_id": r.location_group_id,
        "location_code": r.location_code,
        "location_name": r.location_name,
        "location_full_name": r.location_full_name,
        "depth": r.depth,
        "detail_flag": r.detail_flag,
        "parent_id": r.parent_id,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
