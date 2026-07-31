"""物料盘点 (scm_inventory_check) 业务服务"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Tuple

from sqlalchemy import select, func, desc, or_, String as SAString, text, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.inventory import Inventory
from app.models.basicdata.material import Material
from app.models.material.inventory_check import StockCheck, StockCheckItem
from app.models.order.sale_order import SaleOrder
from app.services.order.order_materials_service import get_order_product_materials, MATERIAL_PROPERTY_LABELS


class StockCheckPermissionError(Exception):
    """盘点单修改权限不足"""
    pass


def _current_user_id(user: Optional[dict]) -> Optional[int]:
    """从 current_user 取 user_id：PermissionChecker 返回的 JWT payload 用 'sub'，
    get_current_user 用 'user_id'。统一兼容。"""
    if not user:
        return None
    v = user.get("user_id")
    if v is None:
        v = user.get("sub")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _user_can_edit(head: Optional[StockCheck], user: Optional[dict]) -> bool:
    """创建人 / 共同盘点人 / admin 可改

    旧盘点单(无 created_by_user_id 且无共同盘点人)回退到"有权限即可改"，保持向后兼容。
    """
    if head is None:
        return False
    if not user:
        return True  # 内部调用无 user 上下文，放行（兼容）
    if user.get("role") == "admin":
        return True
    has_owner = head.created_by_user_id is not None or bool(head.co_checker_user_ids)
    if not has_owner:
        return True
    uid = _current_user_id(user)
    if uid is None:
        return False
    if head.created_by_user_id is not None and int(head.created_by_user_id) == uid:
        return True
    co = head.co_checker_user_ids or []
    if any(x is not None and int(x) == uid for x in co):
        return True
    return False


async def _assert_can_edit(db: AsyncSession, check_id: int, user: Optional[dict]) -> None:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if head is None:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if not _user_can_edit(head, user):
        raise StockCheckPermissionError("无修改权限：仅创建人、共同盘点人或管理员可修改")


async def _resolve_user_names(db: AsyncSession, user_ids: List[int]) -> Dict[int, str]:
    """sys_user.id -> 展示名(优先 emp_name，其次 username)"""
    ids = [int(x) for x in (user_ids or []) if x is not None]
    if not ids:
        return {}
    from app.models.basicdata.user import SysUser
    from app.models.basicdata.employee import Employee
    res = await db.execute(
        select(SysUser.id, SysUser.username, Employee.emp_name)
        .outerjoin(Employee, Employee.emp_code == SysUser.emp_code)
        .where(SysUser.id.in_(ids))
    )
    return {int(r.id): (r.emp_name or r.username) for r in res.all()}


async def list_co_checker_candidates(db: AsyncSession) -> List[Dict]:
    """共同盘点人候选：全部在职系统用户（含员工姓名/组织/岗位），用于按组织架构选人。"""
    from app.models.basicdata.user import SysUser
    from app.models.basicdata.employee import Employee
    from app.models.basicdata.organization import Organization
    from app.models.basicdata.position import Position
    from sqlalchemy import cast, String as SAString
    res = await db.execute(
        select(
            SysUser.id, SysUser.username,
            Employee.emp_name, Organization.org_name, Position.position_name,
        )
        .outerjoin(Employee, Employee.emp_code == SysUser.emp_code)
        .outerjoin(Organization, cast(Employee.org_id, SAString) == Organization.oa_org_id)
        .outerjoin(Position, Employee.position_id == Position.id)
        .where(SysUser.is_active.is_(True))
        .order_by(Organization.org_name.nulls_last(), Employee.emp_code)
    )
    out: List[Dict] = []
    for r in res.all():
        out.append({
            "user_id": int(r.id),
            "name": r.emp_name or r.username,
            "org_name": r.org_name or "未分组",
            "position_name": r.position_name,
        })
    return out


def _gen_check_no(seq: int) -> str:
    return f"PD{datetime.now().strftime('%Y%m%d')}-{seq:03d}"


async def _get_stock_by_warehouse(
    db: AsyncSession,
    material_ids: List[int],
) -> Dict[Tuple[int, int], Tuple[str, Decimal, Optional[datetime]]]:
    """按 (material_id, wh_id) 分组聚合 scm_inventory.qty_on_hand。

    同仓多库位的 qty_on_hand 求和；返回 {(mid, wh_id): (wh_name, qty, updated_at)}。
    updated_at 取该组库存的最大更新时间(用于快照库存时间)。
    仅包含 scm_inventory 中存在记录的仓（含 qty=0 的仓）。
    """
    if not material_ids:
        return {}
    result = await db.execute(
        select(
            Inventory.material_id,
            Inventory.wh_id,
            func.max(Inventory.wh_name).label("wh_name"),
            func.coalesce(func.sum(Inventory.qty_on_hand), 0).label("wh_qty"),
            func.max(Inventory.updated_at).label("wh_updated"),
        )
        .where(Inventory.material_id.in_(material_ids))
        .group_by(Inventory.material_id, Inventory.wh_id)
    )
    out: Dict[Tuple[int, int], Tuple[str, Decimal, Optional[datetime]]] = {}
    for row in result.all():
        wh_name = (row.wh_name or "").strip() or f"WH#{row.wh_id}"
        out[(int(row.material_id), int(row.wh_id))] = (
            wh_name,
            Decimal(str(row.wh_qty or 0)),
            row.wh_updated,
        )
    return out


async def _get_stock_aggregated_by_material_id(
    db: AsyncSession,
    material_ids: List[int],
) -> Dict[int, Decimal]:
    """按 material_id 聚合 scm_inventory.qty_on_hand（跨仓求和）。

    用于 MaterialPickerModal 候选列表等需要单值的场景。
    """
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


def _split_stock_by_warehouse(
    stock_map: Dict[Tuple[int, int], Tuple[str, Decimal, Optional[datetime]]],
    material_ids: List[int],
) -> Dict[int, List[Tuple[int, str, Decimal, Optional[datetime]]]]:
    """将 _get_stock_by_warehouse 的结果按 material_id 分组成
    {material_id: [(wh_id, wh_name, qty, updated_at), ...]}。
    """
    grouped: Dict[int, List[Tuple[int, str, Decimal, Optional[datetime]]]] = {m: [] for m in material_ids}
    for (mid, wh_id), (wh_name, qty, t) in stock_map.items():
        if mid in grouped:
            grouped[mid].append((wh_id, wh_name, qty, t))
    for mid in grouped:
        grouped[mid].sort(key=lambda x: (x[1], x[0]))
    return grouped


async def _get_recent_checked_by_warehouse(
    db: AsyncSession,
    keys: List[Tuple[Optional[int], Optional[int]]],
) -> Dict[Tuple[Optional[int], Optional[int]], Dict]:
    """对每个 (material_id, wh_id)，查最近一条 actual_qty 非空且所在盘点单未取消的行。

    返回 {(mid, wh_id): {"actual_qty": Decimal, "check_no": str, "check_date": date}}。
    wh_id 为 None 时按 IS NULL 匹配（未入库合成行）。
    PostgreSQL 用 DISTINCT ON 一次取齐。
    """
    if not keys:
        return {}
    mids = [k[0] for k in keys]
    sql = text(
        """
        SELECT DISTINCT ON (ic.material_id, ic.wh_id)
               ic.material_id AS mid,
               ic.wh_id       AS whid,
               ic.actual_qty  AS actual_qty,
               h.check_no     AS check_no,
               h.check_date   AS check_date
        FROM scm_inventory_check_item ic
        JOIN scm_inventory_check h ON h.id = ic.check_id
        WHERE ic.material_id = ANY(:mids)
          AND ic.actual_qty IS NOT NULL
          AND h.status <> 'cancelled'
        ORDER BY ic.material_id, ic.wh_id, h.check_date DESC, h.created_at DESC
        """
    )
    rows = (await db.execute(sql, {"mids": mids})).all()
    out: Dict[Tuple[Optional[int], Optional[int]], Dict] = {}
    for r in rows:
        mid = int(r.mid) if r.mid is not None else None
        whid = int(r.whid) if r.whid is not None else None
        out[(mid, whid)] = {
            "actual_qty": Decimal(str(r.actual_qty)),
            "check_no": r.check_no,
            "check_date": r.check_date,
        }
    return out


async def enrich_items_assoc(db: AsyncSession, items: List[StockCheckItem]) -> None:
    mids = [int(it.material_id) for it in items if it.material_id is not None]
    if not mids:
        for it in items:
            it.material_property_label = None
            it.material_type = None
            it.warehouses = None
        return
    mat_res = await db.execute(
        select(
            Material.erp_material_id,
            Material.material_property,
            Material.material_type,
        ).where(Material.erp_material_id.in_(mids))
    )
    prop_map: Dict[int, Optional[int]] = {}
    type_map: Dict[int, Optional[str]] = {}
    for r in mat_res.all():
        prop_map[int(r.erp_material_id)] = r.material_property
        type_map[int(r.erp_material_id)] = r.material_type
    for it in items:
        mid = int(it.material_id) if it.material_id is not None else None
        mp = prop_map.get(mid) if mid is not None else None
        it.material_property_label = MATERIAL_PROPERTY_LABELS.get(mp, str(mp)) if mp is not None else None
        it.material_type = type_map.get(mid) if mid is not None else None
        it.warehouses = None


async def enrich_live_qty(db: AsyncSession, items: List[StockCheckItem]) -> None:
    """为每条明细注入实时库存 live_qty(读时计算,不落库)。

    优先按与快照相同的 (material_id, wh_id) 查询 scm_inventory.qty_on_hand;
    老盘点单明细无 wh_id 时,回退到按物料跨仓聚合,保证兼容。
    """
    mids = [int(it.material_id) for it in items if it.material_id is not None]
    stock_map = await _get_stock_by_warehouse(db, mids) if mids else {}
    none_wh_mids = list({
        int(it.material_id) for it in items
        if it.material_id is not None and it.wh_id is None
    })
    agg_map = (
        await _get_stock_aggregated_by_material_id(db, none_wh_mids) if none_wh_mids else {}
    )
    for it in items:
        mid = int(it.material_id) if it.material_id is not None else None
        wh_id = int(it.wh_id) if it.wh_id is not None else None
        if mid is None:
            it.live_qty = Decimal("0")
        elif wh_id is not None:
            entry = stock_map.get((mid, wh_id))
            it.live_qty = entry[1] if entry else Decimal("0")
        else:
            it.live_qty = agg_map.get(mid, Decimal("0"))


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
    selected_products: Optional[List[Dict[str, Optional[str]]]] = None,
    co_checker_user_ids: Optional[List[int]] = None,
) -> StockCheck:
    """从订单创建盘点单: BOM 多层展开 + 每节点一行 + 写头/行

    selected_products: 每项 {"product_code": str|None, "bom_no": str|None};
        None 表示全部产品行;非空则只展开匹配的产品行。
    co_checker_user_ids: 共同盘点人(sys_user.id)列表，可与创建人共同修改盘点单。
    """
    order = (await db.execute(select(SaleOrder.id).where(SaleOrder.order_no == order_no))).scalar_one_or_none()
    if not order:
        raise ValueError(f"订单 {order_no} 不存在")

    line_materials = await get_order_product_materials(db, order_no=order_no)
    if selected_products:
        sel = {(s.get("product_code"), s.get("bom_no")) for s in selected_products}
        line_materials = [
            lm for lm in line_materials
            if (lm.product_code, lm.bom_no) in sel
        ]
        if not line_materials:
            raise ValueError("所选产品未匹配到任何产品行,无法创建盘点单")
    # 递归展开整棵 BOM，收集所有带 material_id 的节点(含父件/子件各层级)。
    # 每个 BOM 节点写一行盘点明细(不再按 material_id 聚合)，level 标识层级。
    def _walk(nodes, level):
        for n in (nodes or []):
            yield n, level
            yield from _walk(getattr(n, "children", None) or [], level + 1)

    nodes: List = []  # (line_materials_row, bom_node, level)
    for lm in line_materials:
        for n, lvl in _walk(lm.materials or [], 1):
            if n.material_id:
                nodes.append((lm, n, lvl))

    if not nodes:
        raise ValueError(f"订单 {order_no} 未展开出任何物料,无法创建盘点单")

    unique_mids: List[int] = []
    seen: set = set()
    for _, n, _ in nodes:
        mid = int(n.material_id)
        if mid not in seen:
            seen.add(mid)
            unique_mids.append(mid)
    stock_map = await _get_stock_by_warehouse(db, unique_mids)
    warehouses_by_mid = _split_stock_by_warehouse(stock_map, unique_mids)

    # 记录本次盘点覆盖的产品行(用于"该订单哪些产品已盘点"的可追溯性)
    covered_products = [
        {
            "product_code": lm.product_code,
            "bom_no": lm.bom_no,
            "line_no": lm.line_no,
            "product_name": lm.product_name,
            "order_qty": lm.order_qty,
        }
        for lm in line_materials
    ]

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
        created_by_user_id=_current_user_id(current_user),
        remark=remark,
        covered_products=covered_products,
        co_checker_user_ids=co_checker_user_ids,
    )
    db.add(head)
    await db.flush()

    # 1) 收敛：同一 (material_id, wh_id) 跨 BOM 节点/产品只取一行（取首次出现的物料信息）
    dedup_order: List[Tuple[Optional[int], Optional[int]]] = []
    dedup_row_meta: Dict[Tuple[int, Optional[int]], Dict] = {}
    for lm, n, lvl in nodes:
        mid = int(n.material_id)
        warehouses = warehouses_by_mid.get(mid, [])
        if warehouses:
            for wh_id, wh_name, sys_q, sys_t in warehouses:
                k = (mid, wh_id)
                if k in dedup_row_meta:
                    continue
                dedup_row_meta[k] = {
                    "material_code": n.material_code,
                    "material_name": n.material_name,
                    "spec_model": n.spec_model,
                    "unit": n.unit,
                    "system_qty": sys_q,
                    "system_qty_time": sys_t,
                    "wh_name": wh_name,
                }
                dedup_order.append(k)
        else:
            k = (mid, None)
            if k in dedup_row_meta:
                continue
            dedup_row_meta[k] = {
                "material_code": n.material_code,
                "material_name": n.material_name,
                "spec_model": n.spec_model,
                "unit": n.unit,
                "system_qty": Decimal("0"),
                "system_qty_time": None,
                "wh_name": "(未入库)",
            }
            dedup_order.append(k)

    # 2) 查近盘预填补
    from app.core.config import get_settings
    skip_days = int(get_settings().STOCK_CHECK_RECENT_SKIP_DAYS)
    recent_map = await _get_recent_checked_by_warehouse(db, dedup_order)
    today = date.today()

    # 3) 写行
    item_rows: List[StockCheckItem] = []
    for k in dedup_order:
        mid, wh_id = k
        meta = dedup_row_meta[k]
        recent = recent_map.get(k)
        prefill = (
            recent is not None
            and recent["check_date"] is not None
            and (today - recent["check_date"]).days <= skip_days
        )
        if prefill:
            actual_q = recent["actual_qty"]
            item_rows.append(StockCheckItem(
                check_id=head.id,
                line_no=None,
                level=None,
                material_id=mid,
                material_code=meta["material_code"],
                material_name=meta["material_name"],
                spec_model=meta["spec_model"],
                unit=meta["unit"],
                req_qty=Decimal("0"),
                system_qty=meta["system_qty"],
                system_qty_time=meta.get("system_qty_time"),
                wh_id=wh_id,
                wh_name=meta["wh_name"],
                actual_qty=actual_q,
                diff_qty=Decimal(str(actual_q)) - Decimal(str(meta["system_qty"])),
                is_checked=1,
                checked_at=datetime.utcnow(),
                checked_by="system-recent",
                recent_checked_check_no=recent["check_no"],
                recent_checked_date=recent["check_date"],
            ))
        else:
            item_rows.append(StockCheckItem(
                check_id=head.id,
                line_no=None,
                level=None,
                material_id=mid,
                material_code=meta["material_code"],
                material_name=meta["material_name"],
                spec_model=meta["spec_model"],
                unit=meta["unit"],
                req_qty=Decimal("0"),
                system_qty=meta["system_qty"],
                system_qty_time=meta.get("system_qty_time"),
                wh_id=wh_id,
                wh_name=meta["wh_name"],
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
    co_checker_user_ids: Optional[List[int]] = None,
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

    stock_map = await _get_stock_by_warehouse(db, [m.erp_material_id for m in materials])
    warehouses_by_mid = _split_stock_by_warehouse(stock_map, [m.erp_material_id for m in materials])

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
        created_by_user_id=_current_user_id(current_user),
        remark=remark,
        co_checker_user_ids=co_checker_user_ids,
    )
    db.add(head)
    await db.flush()

    item_rows: List[StockCheckItem] = []
    for m in materials:
        mid = m.erp_material_id
        warehouses = warehouses_by_mid.get(mid, [])
        if warehouses:
            for wh_id, wh_name, sys_q, sys_t in warehouses:
                item_rows.append(StockCheckItem(
                    check_id=head.id,
                    line_no=None,
                    material_id=mid,
                    material_code=m.material_code,
                    material_name=m.material_name,
                    spec_model=m.spec_model,
                    unit=m.unit_of_measure,
                    req_qty=Decimal("0"),
                    system_qty=sys_q,
                    system_qty_time=sys_t,
                    wh_id=wh_id,
                    wh_name=wh_name,
                    actual_qty=None,
                    diff_qty=Decimal("0"),
                    is_checked=0,
                ))
        else:
            item_rows.append(StockCheckItem(
                check_id=head.id,
                line_no=None,
                material_id=mid,
                material_code=m.material_code,
                material_name=m.material_name,
                spec_model=m.spec_model,
                unit=m.unit_of_measure,
                req_qty=Decimal("0"),
                system_qty=Decimal("0"),
                wh_id=None,
                wh_name="(未入库)",
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
    stock_map = await _get_stock_aggregated_by_material_id(db, erp_ids)

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
    force_recount: Optional[bool] = None,
    current_user: Optional[dict] = None,
) -> StockCheckItem:
    item = (await db.execute(select(StockCheckItem).where(StockCheckItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise ValueError(f"盘点行 {item_id} 不存在")
    await _assert_can_edit(db, item.check_id, current_user)
    if force_recount:
        item.recent_checked_check_no = None
        item.recent_checked_date = None
        item.is_checked = 0
        item.checked_at = None
        item.checked_by = None
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
            force_recount=it.get("force_recount"),
            current_user=current_user,
        )
        n += 1
    return n


async def complete_stock_check(db: AsyncSession, check_id: int, current_user: dict) -> StockCheck:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if not _user_can_edit(head, current_user):
        raise StockCheckPermissionError("无修改权限：仅创建人、共同盘点人或管理员可修改")
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
    if not _user_can_edit(head, current_user):
        raise StockCheckPermissionError("无修改权限：仅创建人、共同盘点人或管理员可修改")
    if head.status == "completed":
        raise ValueError("已完结的盘点单不能取消")
    head.status = "cancelled"
    await db.flush()
    return head


async def set_co_checkers(
    db: AsyncSession, check_id: int, user_ids: List[int], current_user: dict,
) -> StockCheck:
    """设置共同盘点人名单（仅创建人/admin 可改名单）。"""
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    uid = _current_user_id(current_user)
    is_creator = (
        head.created_by_user_id is not None
        and uid is not None
        and int(head.created_by_user_id) == uid
    )
    if not (current_user.get("role") == "admin" or is_creator):
        raise StockCheckPermissionError("仅创建人或管理员可修改共同盘点人名单")
    cleaned: List[int] = []
    seen: set = set()
    for x in (user_ids or []):
        try:
            v = int(x)
        except (TypeError, ValueError):
            continue
        if v > 0 and v not in seen:
            seen.add(v)
            cleaned.append(v)
    head.co_checker_user_ids = cleaned
    await db.flush()
    return head


async def refresh_order_bom(db: AsyncSession, check_id: int, current_user: dict) -> StockCheck:
    """对 in-progress 的订单盘点单重新展开 BOM，补入之前未纳入的子 BOM 物料。

    - 仅订单盘点单、仅 open/in_progress 状态可用。
    - 按 head.covered_products 筛选产品行（为空则全部）。
    - 保留已有明细及已录入数据；缺失的 material_id 取首次出现位置补入一行（带 level）。
    - 权限：创建人 / 共同盘点人 / admin（沿用 _user_can_edit）。
    """
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if head.check_type != "order" or not head.order_no:
        raise ValueError("仅订单盘点单支持刷新BOM")
    if head.status not in ("open", "in_progress"):
        raise ValueError("仅待盘点/盘点中的单据可刷新BOM")
    if not _user_can_edit(head, current_user):
        raise StockCheckPermissionError("无修改权限：仅创建人、共同盘点人或管理员可修改")

    line_materials = await get_order_product_materials(db, order_no=head.order_no)
    if head.covered_products:
        sel = {(c.get("product_code"), c.get("bom_no")) for c in head.covered_products}
        line_materials = [lm for lm in line_materials if (lm.product_code, lm.bom_no) in sel]
    if not line_materials:
        raise ValueError("所覆盖的产品行未展开出任何物料")

    existing_res = await db.execute(
        select(StockCheckItem.material_id).where(StockCheckItem.check_id == check_id)
    )
    existing_mids = {int(mid) for mid in existing_res.scalars().all() if mid is not None}

    def _walk(nodes, level):
        for n in (nodes or []):
            if n.material_id:
                yield n, level
            yield from _walk(getattr(n, "children", None) or [], level + 1)

    candidates = []
    added_mids: set = set()
    for lm in line_materials:
        for n, lvl in _walk(lm.materials or [], 1):
            mid = int(n.material_id)
            if mid in existing_mids or mid in added_mids:
                continue
            added_mids.add(mid)
            candidates.append((mid, n, lvl))
    if not candidates:
        return head

    stock_map = await _get_stock_by_warehouse(db, list(added_mids))
    warehouses_by_mid = _split_stock_by_warehouse(stock_map, list(added_mids))

    # 收敛新增 (material_id, wh_id)，跳过已存在的
    new_keys: List[Tuple[int, Optional[int]]] = []
    new_meta: Dict[Tuple[int, Optional[int]], Dict] = {}
    for mid, n, lvl in candidates:
        warehouses = warehouses_by_mid.get(mid, [])
        if warehouses:
            for wh_id, wh_name, sys_q, sys_t in warehouses:
                k = (mid, wh_id)
                if k in new_meta:
                    continue
                exists = (await db.execute(
                    select(func.count(StockCheckItem.id)).where(
                        StockCheckItem.check_id == check_id,
                        StockCheckItem.material_id == mid,
                        StockCheckItem.wh_id == wh_id,
                    )
                )).scalar_one()
                if exists:
                    continue
                new_meta[k] = {
                    "material_code": n.material_code,
                    "material_name": n.material_name,
                    "spec_model": n.spec_model,
                    "unit": n.unit,
                    "system_qty": sys_q,
                    "system_qty_time": sys_t,
                    "wh_name": wh_name,
                }
                new_keys.append(k)
        else:
            k = (mid, None)
            if k in new_meta:
                continue
            exists = (await db.execute(
                select(func.count(StockCheckItem.id)).where(
                    StockCheckItem.check_id == check_id,
                    StockCheckItem.material_id == mid,
                    StockCheckItem.wh_id.is_(None),
                )
            )).scalar_one()
            if exists:
                continue
            new_meta[k] = {
                "material_code": n.material_code,
                "material_name": n.material_name,
                "spec_model": n.spec_model,
                "unit": n.unit,
                "system_qty": Decimal("0"),
                "system_qty_time": None,
                "wh_name": "(未入库)",
            }
            new_keys.append(k)

    if not new_keys:
        await db.flush()
        await _refresh_check_aggregates(db, check_id)
        await db.flush()
        return head

    from app.core.config import get_settings
    skip_days = int(get_settings().STOCK_CHECK_RECENT_SKIP_DAYS)
    recent_map = await _get_recent_checked_by_warehouse(db, new_keys)
    today = date.today()

    for k in new_keys:
        mid, wh_id = k
        meta = new_meta[k]
        recent = recent_map.get(k)
        prefill = (
            recent is not None
            and recent["check_date"] is not None
            and (today - recent["check_date"]).days <= skip_days
        )
        if prefill:
            actual_q = recent["actual_qty"]
            db.add(StockCheckItem(
                check_id=check_id,
                line_no=None,
                level=None,
                material_id=mid,
                material_code=meta["material_code"],
                material_name=meta["material_name"],
                spec_model=meta["spec_model"],
                unit=meta["unit"],
                req_qty=Decimal("0"),
                system_qty=meta["system_qty"],
                system_qty_time=meta.get("system_qty_time"),
                wh_id=wh_id,
                wh_name=meta["wh_name"],
                actual_qty=actual_q,
                diff_qty=Decimal(str(actual_q)) - Decimal(str(meta["system_qty"])),
                is_checked=1,
                checked_at=datetime.utcnow(),
                checked_by="system-recent",
                recent_checked_check_no=recent["check_no"],
                recent_checked_date=recent["check_date"],
            ))
        else:
            db.add(StockCheckItem(
                check_id=check_id,
                line_no=None,
                level=None,
                material_id=mid,
                material_code=meta["material_code"],
                material_name=meta["material_name"],
                spec_model=meta["spec_model"],
                unit=meta["unit"],
                req_qty=Decimal("0"),
                system_qty=meta["system_qty"],
                system_qty_time=meta.get("system_qty_time"),
                wh_id=wh_id,
                wh_name=meta["wh_name"],
                actual_qty=None,
                diff_qty=Decimal("0"),
                is_checked=0,
            ))
    await db.flush()
    await _refresh_check_aggregates(db, check_id)
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
    await enrich_items_assoc(db, head.items)
    await enrich_live_qty(db, head.items)
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
    """查询某物料被哪些盘点单盘点过的历史记录 (不含已取消)。
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
        .where(StockCheck.status != "cancelled")
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


async def get_stock_check_stats(
    db: AsyncSession,
    *,
    check_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[List[str]] = None,
) -> Dict:
    """盘盈盘亏统计（仅 is_checked=1 的已盘点行，排除已取消单）。
    返回 dict 供路由层构造 StockCheckStats。"""
    conds = [
        StockCheckItem.is_checked == 1,
        StockCheck.status != "cancelled",
    ]
    if check_type:
        conds.append(StockCheck.check_type == check_type)
    if date_from:
        conds.append(StockCheck.check_date >= date_from)
    if date_to:
        conds.append(StockCheck.check_date <= date_to)
    if status:
        conds.append(StockCheck.status.in_(status))

    gain_c = func.sum(case((StockCheckItem.diff_qty > 0, 1), else_=0)).label("gain_count")
    loss_c = func.sum(case((StockCheckItem.diff_qty < 0, 1), else_=0)).label("loss_count")
    flat_c = func.sum(case((StockCheckItem.diff_qty == 0, 1), else_=0)).label("flat_count")
    total_gain = func.coalesce(
        func.sum(case((StockCheckItem.diff_qty > 0, StockCheckItem.diff_qty), else_=0)), 0
    ).label("total_gain_qty")
    total_loss = func.coalesce(
        func.sum(case((StockCheckItem.diff_qty < 0, StockCheckItem.diff_qty), else_=0)), 0
    ).label("total_loss_qty")
    total_checked = func.count(StockCheckItem.id).label("total_checked")

    q1 = (
        select(gain_c, loss_c, flat_c, total_gain, total_loss, total_checked)
        .join(StockCheck, StockCheck.id == StockCheckItem.check_id)
        .where(*conds)
    )
    row = (await db.execute(q1)).one()

    q2 = (
        select(
            StockCheckItem.material_code,
            func.max(StockCheckItem.material_name).label("material_name"),
            func.max(StockCheckItem.unit).label("unit"),
            func.sum(StockCheckItem.diff_qty).label("diff_qty"),
        )
        .join(StockCheck, StockCheck.id == StockCheckItem.check_id)
        .where(*conds, StockCheckItem.material_code.isnot(None))
        .group_by(StockCheckItem.material_code)
        .order_by(func.abs(func.sum(StockCheckItem.diff_qty)).desc())
        .limit(10)
    )
    top_rows = (await db.execute(q2)).all()

    return {
        "total_checked": int(row.total_checked or 0),
        "gain_count": int(row.gain_count or 0),
        "loss_count": int(row.loss_count or 0),
        "flat_count": int(row.flat_count or 0),
        "total_gain_qty": float(row.total_gain_qty or 0),
        "total_loss_qty": float(row.total_loss_qty or 0),
        "top_diff_materials": [
            {
                "material_code": r.material_code or "",
                "material_name": r.material_name or "",
                "diff_qty": float(r.diff_qty or 0),
                "unit": r.unit,
            }
            for r in top_rows
        ],
    }
