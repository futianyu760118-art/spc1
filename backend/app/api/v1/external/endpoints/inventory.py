"""库存对外接口

为外部系统（如 WMS / ERP / 财务系统）提供即时库存明细查询。
基于 Inventory 表（scm_inventory，material_id + wh_id + location_id 唯一）。
对外只暴露精简字段集与常用筛选条件，字段集合独立于表结构变更。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.basicdata.inventory import Inventory

from ..registry import register_external, ExternalCallContext


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@register_external(
    "inventory.list",
    "库存列表",
    method="GET",
    path="/inventory/list",
    description="即时库存明细查询（物料×仓库×库位），支持关键字、物料/仓库/批次筛选、增量同步",
    tags=["库存"],
)
async def inventory_list(ctx: ExternalCallContext) -> dict:
    """库存列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（物料编码 / 物料名称 / 仓库名称 模糊匹配）
        material_code: 物料编码精确匹配
        wh_code: 仓库编码精确匹配
        batch_no: 批次号精确匹配
        updated_after: 增量同步，仅返回 updated_at >= 此时间的记录 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    material_code = params.get("material_code")
    wh_code = params.get("wh_code")
    batch_no = params.get("batch_no")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(Inventory)
    count_query = select(func.count()).select_from(query.subquery())

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            Inventory.material_code.ilike(like_expr),
            Inventory.material_name.ilike(like_expr),
            Inventory.wh_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = select(func.count()).select_from(query.subquery())

    if material_code:
        query = query.where(Inventory.material_code == material_code)
        count_query = select(func.count()).select_from(query.subquery())

    if wh_code:
        query = query.where(Inventory.wh_code == wh_code)
        count_query = select(func.count()).select_from(query.subquery())

    if batch_no:
        query = query.where(Inventory.batch_no == batch_no)
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(Inventory.updated_at >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Inventory.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "material_id": r.material_id,
        "material_code": r.material_code,
        "material_name": r.material_name,
        "wh_id": r.wh_id,
        "wh_code": r.wh_code,
        "wh_name": r.wh_name,
        "location_id": r.location_id,
        "location_name": r.location_name,
        "qty_on_hand": float(r.qty_on_hand) if r.qty_on_hand is not None else None,
        "locked_qty": float(r.locked_qty) if r.locked_qty is not None else None,
        "balance_qty": float(r.balance_qty) if r.balance_qty is not None else None,
        "qty_in_transit": float(r.qty_in_transit) if r.qty_in_transit is not None else None,
        "unit_price": float(r.unit_price) if r.unit_price is not None else None,
        "ending_balance": float(r.ending_balance) if r.ending_balance is not None else None,
        "batch_no": r.batch_no,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
