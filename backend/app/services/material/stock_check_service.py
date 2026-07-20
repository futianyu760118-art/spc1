"""物料盘点 (scm_inventory_check) 业务服务"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict

from sqlalchemy import select, func, desc, or_, String as SAString
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.inventory import Inventory
from app.models.basicdata.bom_detail import BomDetail
from app.models.basicdata.material import Material
from app.models.material.inventory_check import StockCheck, StockCheckItem
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.services.order.order_materials_service import get_order_product_materials


def _gen_check_no(seq: int) -> str:
    return f"PD{datetime.now().strftime('%Y%m%d')}-{seq:03d}"


async def _get_stock_by_material_id(
    db: AsyncSession,
    material_ids: List[int],
) -> Dict[int, Decimal]:
    """按 material_id 聚合 scm_inventory.qty_on_hand"""
    if not material_ids:
        return {}
    result = await db.execute(
        select(
            Inventory.material_id,
            func.coalesce(func.sum(Inventory.qty_on_hand), 0).label("total_qty"),
        )
        .where(Inventory.material_id.in_(material_ids))
        .group_by(Inventory.material_id)
    )
    return {row.material_id: Decimal(str(row.total_qty or 0)) for row in result}


async def _refresh_check_aggregates(db: AsyncSession, check_id: int) -> None:
    """刷新头表 total_materials / checked_materials / total_diff_qty"""
    items_agg = await db.execute(
        select(
            func.count(StockCheckItem.id).label("total"),
            func.coalesce(func.sum(StockCheckItem.is_checked), 0).label("checked"),
            func.coalesce(func.sum(StockCheckItem.diff_qty), 0).label("diff"),
        ).where(StockCheckItem.check_id == check_id)
    )
    row = items_agg.one()
    head = await db.execute(select(StockCheck).where(StockCheck.id == check_id))
    head_obj: Optional[StockCheck] = head.scalar_one_or_none()
    if head_obj:
        head_obj.total_materials = int(row.total or 0)
        head_obj.checked_materials = int(row.checked or 0)
        head_obj.total_diff_qty = Decimal(str(row.diff or 0))


async def _next_seq_for_today(db: AsyncSession) -> int:
    today_prefix = f"PD{datetime.now().strftime('%Y%m%d')}-"
    res = await db.execute(
        select(StockCheck.check_no).where(StockCheck.check_no.like(f"{today_prefix}%"))
    )
    existing = [r[0] for r in res.all()]
    max_seq = 0
    for no in existing:
        try:
            seq = int(no.split("-")[-1])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, IndexError):
            pass
    return max_seq + 1


async def create_stock_check_from_order(
    db: AsyncSession,
    order_no: str,
    current_user: dict,
    *,
    title: Optional[str] = None,
    check_date: Optional[date] = None,
    remark: Optional[str] = None,
) -> StockCheck:
    """从订单创建盘点单: BOM 展开 + 聚合 system_qty + 写头/行"""
    order = (await db.execute(select(SaleOrder.id).where(SaleOrder.order_no == order_no))).scalar_one_or_none()
    if not order:
        raise ValueError(f"订单 {order_no} 不存在")

    line_materials = await get_order_product_materials(db, order_no=order_no)
    agg: Dict[int, Dict] = {}
    for lm in line_materials:
        for it in (lm.materials or []):
            if not it.material_id:
                continue
            mid = int(it.material_id)
            entry = agg.setdefault(mid, {
                "line_no": lm.line_no,
                "material_id": mid,
                "material_code": it.material_code,
                "material_name": it.material_name,
                "spec_model": it.spec_model,
                "unit": it.unit,
                "req_qty": Decimal("0"),
            })
            entry["req_qty"] += Decimal(str(it.req_qty or 0))

    if not agg:
        raise ValueError(f"订单 {order_no} 未展开出任何物料,无法创建盘点单")

    stock_map = await _get_stock_by_material_id(db, list(agg.keys()))

    seq = await _next_seq_for_today(db)
    check_no = _gen_check_no(seq)

    head = StockCheck(
        check_no=check_no,
        order_no=order_no,
        title=title or f"{order_no} 盘点 {datetime.now().strftime('%Y-%m-%d')}",
        check_type="order",
        status="in_progress",
        check_date=check_date or date.today(),
        created_by=current_user.get("username", ""),
        remark=remark,
    )
    db.add(head)
    await db.flush()

    item_rows: List[StockCheckItem] = []
    for mid, e in agg.items():
        sys_q = stock_map.get(mid, Decimal("0"))
        item_rows.append(StockCheckItem(
            check_id=head.id,
            line_no=None,
            material_id=mid,
            material_code=e["material_code"],
            material_name=e["material_name"],
            spec_model=e["spec_model"],
            unit=e["unit"],
            req_qty=e["req_qty"],
            system_qty=sys_q,
            actual_qty=None,
            diff_qty=Decimal("0"),
            is_checked=0,
        ))
    db.add_all(item_rows)
    await db.flush()

    await _refresh_check_aggregates(db, head.id)
    await db.flush()
    return head


async def create_stock_check_from_materials(
    db: AsyncSession,
    material_ids: List[int],
    current_user: dict,
    *,
    title: Optional[str] = None,
    check_date: Optional[date] = None,
    remark: Optional[str] = None,
) -> StockCheck:
    """从选定的物料清单创建手动盘点单 (check_type='manual', order_no=NULL)。"""
    if not material_ids:
        raise ValueError("请至少选择一个物料")
    unique_ids = []
    seen = set()
    for mid in material_ids:
        try:
            v = int(mid)
        except (TypeError, ValueError):
            continue
        if v > 0 and v not in seen:
            seen.add(v)
            unique_ids.append(v)
    if not unique_ids:
        raise ValueError("物料 ID 列表无效")

    mat_res = await db.execute(
        select(Material).where(
            Material.erp_material_id.in_(unique_ids),
            Material.is_deleted == 0,
        )
    )
    materials = mat_res.scalars().all()
    if not materials:
        raise ValueError("所选物料均不存在或已删除,无法创建盘点单")
    mat_map = {m.erp_material_id: m for m in materials}

    stock_map = await _get_stock_by_material_id(db, [m.erp_material_id for m in materials])

    seq = await _next_seq_for_today(db)
    check_no = _gen_check_no(seq)

    head = StockCheck(
        check_no=check_no,
        order_no=None,
        title=title or f"手动盘点 {datetime.now().strftime('%Y-%m-%d')}",
        check_type="manual",
        status="in_progress",
        check_date=check_date or date.today(),
        created_by=current_user.get("username", ""),
        remark=remark,
    )
    db.add(head)
    await db.flush()

    item_rows: List[StockCheckItem] = []
    for m in materials:
        sys_q = stock_map.get(m.erp_material_id, Decimal("0"))
        item_rows.append(StockCheckItem(
            check_id=head.id,
            line_no=None,
            material_id=m.erp_material_id,
            material_code=m.material_code,
            material_name=m.material_name,
            spec_model=m.spec_model,
            unit=m.unit_of_measure,
            req_qty=Decimal("0"),
            system_qty=sys_q,
            actual_qty=None,
            diff_qty=Decimal("0"),
            is_checked=0,
        ))
    db.add_all(item_rows)
    await db.flush()

    await _refresh_check_aggregates(db, head.id)
    await db.flush()
    return head


async def list_material_candidates(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
) -> tuple[int, List[Dict]]:
    """手动盘点选物料的候选列表: 来自 scm_material,关联即时库存聚合。"""
    query = select(Material).where(Material.is_deleted == 0)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(
            Material.material_code.ilike(like),
            Material.material_name.ilike(like),
            Material.spec_model.ilike(like),
        ))
    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar() or 0
    rows = (await db.execute(
        query.order_by(Material.material_code).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    erp_ids = [m.erp_material_id for m in rows]
    stock_map = await _get_stock_by_material_id(db, erp_ids)

    items: List[Dict] = []
    for m in rows:
        items.append({
            "erp_material_id": m.erp_material_id,
            "material_code": m.material_code,
            "material_name": m.material_name,
            "spec_model": m.spec_model,
            "unit": m.unit_of_measure,
            "system_qty": stock_map.get(m.erp_material_id, Decimal("0")),
        })
    return int(total), items


async def update_stock_check_item(
    db: AsyncSession,
    item_id: int,
    *,
    actual_qty: Optional[Decimal] = None,
    is_checked: Optional[int] = None,
    remark: Optional[str] = None,
    current_user: Optional[dict] = None,
) -> StockCheckItem:
    item = (await db.execute(select(StockCheckItem).where(StockCheckItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise ValueError(f"盘点行 {item_id} 不存在")
    if actual_qty is not None:
        item.actual_qty = Decimal(str(actual_qty))
    if remark is not None:
        item.remark = remark
    if is_checked is not None:
        item.is_checked = int(is_checked)
        if int(is_checked) == 1:
            item.checked_at = datetime.utcnow()
            if current_user:
                item.checked_by = current_user.get("username", "")
        else:
            item.checked_at = None
            item.checked_by = None
    if item.actual_qty is not None and item.system_qty is not None:
        item.diff_qty = Decimal(str(item.actual_qty)) - Decimal(str(item.system_qty))
    await _refresh_check_aggregates(db, item.check_id)
    await db.flush()
    return item


async def batch_update_items(
    db: AsyncSession,
    check_id: int,
    items: List[dict],
    current_user: dict,
) -> int:
    n = 0
    for it in items:
        if it.get("id") is None:
            continue
        await update_stock_check_item(
            db,
            int(it["id"]),
            actual_qty=it.get("actual_qty"),
            is_checked=it.get("is_checked"),
            remark=it.get("remark"),
            current_user=current_user,
        )
        n += 1
    return n


async def complete_stock_check(db: AsyncSession, check_id: int, current_user: dict) -> StockCheck:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if head.status == "cancelled":
        raise ValueError("已取消的盘点单不能完结")
    if head.status == "completed":
        raise ValueError("已完结的盘点单不能再次完结")
    items_res = await db.execute(
        select(StockCheckItem).where(StockCheckItem.check_id == check_id).order_by(StockCheckItem.id)
    )
    head.items = list(items_res.scalars().all())
    total = (await db.execute(
        select(func.count(StockCheckItem.id)).where(StockCheckItem.check_id == check_id)
    )).scalar_one()
    checked = (await db.execute(
        select(func.count(StockCheckItem.id)).where(
            StockCheckItem.check_id == check_id, StockCheckItem.is_checked == 1
        )
    )).scalar_one()
    if int(total or 0) == 0:
        raise ValueError("盘点单无物料行,无法完结")
    if int(checked or 0) < int(total or 0):
        raise ValueError(f"还有 {int(total) - int(checked)} 行未盘点,无法完结")

    for item in head.items:
        if item.actual_qty is None:
            raise ValueError(f"物料 {item.material_code or item.material_id} 还未录入实盘数,请先填写再完结")

    head.status = "completed"
    head.completed_at = datetime.utcnow()
    head.checked_by = current_user.get("username", "")
    await db.flush()
    return head


async def cancel_stock_check(db: AsyncSession, check_id: int, current_user: dict) -> StockCheck:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if head.status == "completed":
        raise ValueError("已完结的盘点单不能取消")
    head.status = "cancelled"
    await db.flush()
    return head


async def get_stock_check_with_items(db: AsyncSession, check_id: int) -> Optional[StockCheck]:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        return None
    items_res = await db.execute(
        select(StockCheckItem).where(StockCheckItem.check_id == check_id).order_by(StockCheckItem.id)
    )
    head.items = list(items_res.scalars().all())
    return head


async def list_recent_stock_checks(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 10,
    *,
    keyword: Optional[str] = None,
    status: Optional[List[str]] = None,
    check_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> List[StockCheck]:
    SORTABLE = {
        'check_no': StockCheck.check_no,
        'order_no': StockCheck.order_no,
        'check_date': StockCheck.check_date,
        'total_materials': StockCheck.total_materials,
        'checked_materials': StockCheck.checked_materials,
        'total_diff_qty': StockCheck.total_diff_qty,
        'created_at': StockCheck.created_at,
    }
    query = select(StockCheck)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(
            StockCheck.check_no.ilike(like),
            StockCheck.order_no.ilike(like),
            StockCheck.title.ilike(like),
        ))
    if status:
        statuses = [s.strip() for s in status if s and s.strip()]
        if statuses:
            query = query.where(StockCheck.status.in_(statuses))
    if check_type:
        query = query.where(StockCheck.check_type == check_type)
    if date_from:
        query = query.where(StockCheck.check_date >= date_from)
    if date_to:
        query = query.where(StockCheck.check_date <= date_to)
    if sort_by and sort_by in SORTABLE:
        col = SORTABLE[sort_by]
        if sort_order == 'asc':
            query = query.order_by(col.asc().nullslast())
        else:
            query = query.order_by(col.desc().nullslast())
    else:
        query = query.order_by(StockCheck.created_at.desc())
    rows = (await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(rows)


async def list_stock_checks_by_order(db: AsyncSession, order_no: str) -> List[StockCheck]:
    res = await db.execute(
        select(StockCheck).where(StockCheck.order_no == order_no).order_by(desc(StockCheck.created_at))
    )
    return list(res.scalars().all())


async def get_material_history(
    db: AsyncSession,
    material_id: int,
    limit: int = 100,
) -> List[Dict]:
    """查询某物料被哪些盘点单盘点过的历史记录 (含已完成/进行中/已取消)。
    返回字典列表,字段与 MaterialHistoryItem 一致;含 customer 来自 sale_order。"""
    sql = (
        select(
            StockCheck.check_no,
            StockCheck.order_no,
            StockCheck.status,
            StockCheck.check_date,
            StockCheck.completed_at,
            StockCheck.created_at,
            StockCheck.created_by,
            StockCheckItem.actual_qty,
        )
        .join(StockCheck, StockCheck.id == StockCheckItem.check_id)
        .where(StockCheckItem.material_id == material_id)
        .order_by(StockCheck.completed_at.desc().nulls_last(), StockCheck.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(sql)).all()

    if not rows:
        return []

    order_nos = sorted({r.order_no for r in rows if r.order_no})
    customer_map: Dict[str, Optional[str]] = {}
    if order_nos:
        from app.models.order.sale_order import SaleOrder
        so_rows = (await db.execute(
            select(SaleOrder.order_no, SaleOrder.customer)
            .where(SaleOrder.order_no.in_(order_nos))
        )).all()
        for so_r in so_rows:
            customer_map.setdefault(so_r.order_no, so_r.customer)

    return [
        {
            "check_no": r.check_no,
            "order_no": r.order_no,
            "customer": customer_map.get(r.order_no),
            "status": r.status,
            "check_date": r.check_date,
            "completed_at": r.completed_at,
            "actual_qty": r.actual_qty,
            "created_at": r.created_at,
            "created_by": r.created_by,
        }
        for r in rows
    ]


async def list_orders_using_material(
    db: AsyncSession,
    material_id: int,
    page: int = 1,
    page_size: int = 20,
    *,
    keyword: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> tuple[int, List[Dict]]:
    """反查: 哪些未关闭/未取消/未发货的销售订单在使用该物料,各需多少。

    通过 scm_bom_detail.material_id -> scm_bom_detail.bom_id -> sale_order_line.bom_id
        -> sale_order 反向联查,计算 req_qty = standard_qty * order_qty。

    返回 (total, items) 元组,items 为字典列表,字段与 MaterialOrderUsageOut 一致。
    """
    SORTABLE = {
        "req_qty": "req_qty",
        "promised_date": "promised_date",
        "order_qty": "order_qty",
    }

    base = (
        select(
            SaleOrder.order_no.label("order_no"),
            SaleOrder.line_no.label("line_no"),
            SaleOrder.customer.label("customer"),
            SaleOrderLine.product_code.label("product_code"),
            SaleOrderLine.product_name.label("product_name"),
            SaleOrderLine.order_qty.label("order_qty"),
            SaleOrderLine.bom_no.label("bom_no"),
            BomDetail.standard_qty.label("standard_qty"),
            (BomDetail.standard_qty * SaleOrderLine.order_qty).label("req_qty"),
            SaleOrder.promised_date.label("promised_date"),
            SaleOrder.status.label("status"),
            SaleOrder.order_nature.label("order_nature"),
        )
        .join(SaleOrderLine, SaleOrderLine.order_no == SaleOrder.order_no)
        .join(BomDetail, BomDetail.bom_id == SaleOrderLine.bom_id.cast(SAString))
        .where(BomDetail.material_id == material_id)
        .where(SaleOrder.is_closed == 0)
        .where(SaleOrder.status != "cancelled")
        .where(SaleOrder.delivery_completed_date.is_(None))
    )

    if keyword:
        like = f"%{keyword}%"
        base = base.where(or_(
            SaleOrder.order_no.ilike(like),
            SaleOrder.customer.ilike(like),
        ))

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0

    sb = (sort_by or "req_qty").lower()
    so = (sort_order or "desc").lower()
    sort_col = SORTABLE.get(sb, "req_qty")
    order_clauses = {
        "req_qty": (BomDetail.standard_qty * SaleOrderLine.order_qty),
        "promised_date": SaleOrder.promised_date,
        "order_qty": SaleOrderLine.order_qty,
    }
    col = order_clauses[sort_col]
    if so == "asc":
        base = base.order_by(col.asc().nullslast())
    else:
        base = base.order_by(col.desc().nullslast())

    rows = (await db.execute(
        base.offset((page - 1) * page_size).limit(page_size)
    )).all()

    items: List[Dict] = []
    for r in rows:
        items.append({
            "order_no": r.order_no,
            "line_no": r.line_no,
            "customer": r.customer,
            "product_code": r.product_code,
            "product_name": r.product_name,
            "order_qty": r.order_qty,
            "bom_no": r.bom_no,
            "standard_qty": r.standard_qty,
            "req_qty": r.req_qty,
            "promised_date": r.promised_date,
            "status": r.status,
            "order_nature": r.order_nature,
        })

    return int(total), items
