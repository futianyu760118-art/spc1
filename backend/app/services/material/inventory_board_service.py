"""库存看板 — 库存聚合查询 service"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import func, select, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.inventory import Inventory
from app.models.basicdata.material import Material
from app.schemas.material.inventory_board import (
    AgingBucket,
    CategoryStockRow,
    InventoryBoardKpi,
    LowStockRow,
    WarehouseStockRow,
)


def _apply_filters(warehouse_id: Optional[int], category: Optional[str]):
    """构建公用 WHERE：scm_inventory + scm_material join"""
    inv = Inventory
    mat = Material
    cond = [inv.material_id == mat.erp_material_id]
    if warehouse_id is not None:
        cond.append(inv.wh_id == warehouse_id)
    if category:
        cond.append(mat.material_type == category)
    return cond


async def get_inventory_overview(
    db: AsyncSession,
    warehouse_id: Optional[int],
    category: Optional[str],
    low_stock_limit: int = 10,
) -> dict:
    """返回 KPI / 仓库分布 / 类别分布 / 库龄 / 低库存 / 筛选下拉"""

    cond = _apply_filters(warehouse_id, category)

    # KPI: 物料数 / 总库存量 / 总库存金额 / 仓库数
    kpi_q = (
        select(
            func.count(func.distinct(Inventory.material_id)).label("material_count"),
            func.coalesce(func.sum(Inventory.qty_on_hand), 0).label("total_qty"),
            func.coalesce(
                func.sum(Inventory.qty_on_hand * Inventory.unit_price), 0
            ).label("total_value"),
            func.count(func.distinct(Inventory.wh_id)).label("warehouse_count"),
        )
        .select_from(Inventory)
        .join(Material, and_(*cond))
    )
    kpi_row = (await db.execute(kpi_q)).one()
    kpi = InventoryBoardKpi(
        material_count=int(kpi_row.material_count or 0),
        total_qty=Decimal(kpi_row.total_qty or 0),
        total_value=Decimal(kpi_row.total_value or 0),
        warehouse_count=int(kpi_row.warehouse_count or 0),
    )

    # 按仓库
    by_wh_q = (
        select(
            Inventory.wh_id.label("wh_id"),
            func.max(Inventory.wh_name).label("wh_name"),
            func.count(func.distinct(Inventory.material_id)).label("material_count"),
            func.coalesce(func.sum(Inventory.qty_on_hand), 0).label("total_qty"),
            func.coalesce(
                func.sum(Inventory.qty_on_hand * Inventory.unit_price), 0
            ).label("total_value"),
        )
        .select_from(Inventory)
        .join(Material, and_(*cond))
        .group_by(Inventory.wh_id)
        .order_by(func.sum(Inventory.qty_on_hand * Inventory.unit_price).desc())
        .limit(50)
    )
    by_warehouse = [
        WarehouseStockRow(
            warehouse_id=int(r.wh_id),
            warehouse_name=r.wh_name or f"仓库#{r.wh_id}",
            material_count=int(r.material_count or 0),
            total_qty=Decimal(r.total_qty or 0),
            total_value=Decimal(r.total_value or 0),
        )
        for r in (await db.execute(by_wh_q)).all()
    ]

    # 按物料类别
    by_cat_q = (
        select(
            Material.material_type.label("category"),
            func.count(func.distinct(Inventory.material_id)).label("material_count"),
            func.coalesce(func.sum(Inventory.qty_on_hand), 0).label("total_qty"),
            func.coalesce(
                func.sum(Inventory.qty_on_hand * Inventory.unit_price), 0
            ).label("total_value"),
        )
        .select_from(Inventory)
        .join(Material, and_(*cond))
        .group_by(Material.material_type)
        .order_by(func.sum(Inventory.qty_on_hand * Inventory.unit_price).desc())
        .limit(50)
    )
    by_category = [
        CategoryStockRow(
            category=r.category or "未分类",
            material_count=int(r.material_count or 0),
            total_qty=Decimal(r.total_qty or 0),
            total_value=Decimal(r.total_value or 0),
        )
        for r in (await db.execute(by_cat_q)).all()
    ]

    # 库龄（基于 last_inbound_at）
    now = datetime.now(timezone.utc)
    age_expr = case(
        (Inventory.last_inbound_at.is_(None), 99999),
        else_=func.extract("day", now - Inventory.last_inbound_at),
    )
    bucket_expr = case(
        (age_expr <= 30, "0-30d"),
        (age_expr <= 90, "31-90d"),
        (age_expr <= 180, "91-180d"),
        else_="180d+",
    )
    aging_q = (
        select(
            bucket_expr.label("bucket"),
            func.count(func.distinct(Inventory.material_id)).label("material_count"),
            func.coalesce(func.sum(Inventory.qty_on_hand), 0).label("total_qty"),
            func.coalesce(
                func.sum(Inventory.qty_on_hand * Inventory.unit_price), 0
            ).label("total_value"),
        )
        .select_from(Inventory)
        .join(Material, and_(*cond))
        .group_by(bucket_expr)
    )
    bucket_order = ["0-30d", "31-90d", "91-180d", "180d+"]
    rows = {(r.bucket or "180d+"): r for r in (await db.execute(aging_q)).all()}
    aging = [
        AgingBucket(
            bucket=b,
            material_count=int((rows.get(b).material_count if rows.get(b) else 0) or 0),
            total_qty=Decimal((rows.get(b).total_qty if rows.get(b) else 0) or 0),
            total_value=Decimal((rows.get(b).total_value if rows.get(b) else 0) or 0),
        )
        for b in bucket_order
    ]

    # 低库存 Top N（按 qty_on_hand 升序，> 0 优先）
    low_q = (
        select(
            Inventory.material_code,
            Inventory.material_name,
            Inventory.wh_name,
            Inventory.qty_on_hand,
            Material.unit_of_measure,
        )
        .select_from(Inventory)
        .join(Material, and_(*cond))
        .where(Inventory.qty_on_hand > 0)
        .order_by(Inventory.qty_on_hand.asc())
        .limit(low_stock_limit)
    )
    low_stock = [
        LowStockRow(
            material_code=r.material_code,
            material_name=r.material_name,
            warehouse_name=r.wh_name or "",
            qty_on_hand=Decimal(r.qty_on_hand or 0),
            unit=r.unit_of_measure,
        )
        for r in (await db.execute(low_q)).all()
    ]

    # 仓库下拉（distinct wh_id + wh_name）
    wh_dd_q = (
        select(
            Inventory.wh_id,
            func.max(Inventory.wh_name).label("wh_name"),
        )
        .group_by(Inventory.wh_id)
        .order_by(Inventory.wh_id)
    )
    warehouses = [
        {"id": int(r.wh_id), "name": r.wh_name or f"仓库#{r.wh_id}"}
        for r in (await db.execute(wh_dd_q)).all()
    ]

    # 类别下拉（distinct material_type）
    cat_dd_q = (
        select(Material.material_type)
        .where(Material.material_type.isnot(None))
        .group_by(Material.material_type)
        .order_by(Material.material_type)
    )
    categories = [r[0] for r in (await db.execute(cat_dd_q)).all() if r[0]]

    return {
        "kpi": kpi,
        "by_warehouse": by_warehouse,
        "by_category": by_category,
        "aging": aging,
        "low_stock": low_stock,
        "warehouses": warehouses,
        "categories": categories,
    }