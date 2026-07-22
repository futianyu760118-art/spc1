"""Material kit analysis service.

外层列表（按订单聚合）基于销售订单表查询；
展开后的物料明细基于 MRP 计划订单，按 sale_order_no + material_code 关联采购订单推导状态。
"""

from datetime import date
from typing import Optional, List
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.material import Material
from app.models.basicdata.inventory import Inventory
from app.models.basicdata.bom import Bom
from app.models.basicdata.bom_detail import BomDetail
from app.models.material.mrp_plan_order import MrpPlanOrder
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.schemas.material.schemas import (
    KitAnalysisItem,
    KitAnalysisMaterialItem,
    BomKitMaterialItem,
    ProductKitSummary,
    OrderProductKitBreakdownOut,
)
from app.services.common.sync_filter import get_purchase_order_sync_filters
# 复用订单物料服务中的状态推断与 PO 汇总逻辑，保证齐套口径一致
from app.services.order.order_materials_service import (
    STATUS_LABELS,
    _kit_met,
    _material_property_label,
    _status,
    _summarize_pos,
    _to_float,
    _expand_bom_tree,
)


def _kit_risk_level(kit_rate: float) -> str:
    if kit_rate >= 1.0:
        return "green"
    if kit_rate >= 0.8:
        return "yellow"
    return "red"


KIT_SORT_KEYS = {
    "order_no",
    "kit_rate",
    "total_materials",
    "received_materials",
    "partial_received_materials",
    "not_ordered_materials",
    "overdue_materials",
    "stagnant_materials",
    "risk_level",
    "promised_date",
}

MATERIAL_SORT_KEYS = {
    "material_code",
    "material_name",
    "material_property",
    "material_type",
    "supplier_name",
    "mrp_qty",
    "po_qty",
    "stock_qty",
    "received_qty",
    "eta",
    "actual_arrival_date",
    "inspection_date",
    "status",
    "is_stagnant",
    "bill_type",
    "bom_demand_qty",
    "transit_qty",
}


# 计划订单单据类型 → 物料属性 映射
BILL_TYPE_TO_MATERIAL_PROPERTY = {
    11010: 1,   # 采购申请 → 外购
    11011: 2,   # 自制生产任务单 → 自制
    11012: 3,   # 委外申请 → 委外加工
}

BILL_TYPE_LABELS = {
    11010: "采购申请",
    11011: "自制",
    11012: "委外申请",
}


def _status_for_plan(bill_type: Optional[int], po_summary) -> str:
    """根据计划订单单据类型推导物料状态。

    11010/11012：需要采购/委外订单，无 PO 视为未下单；
    11011：自制，无 PO 视为自制未排产/未关联。
    """
    material_property = BILL_TYPE_TO_MATERIAL_PROPERTY.get(bill_type, 1)
    return _status(material_property, po_summary)


def _kit_met_for_plan(status: str, bill_type: Optional[int]) -> bool:
    material_property = BILL_TYPE_TO_MATERIAL_PROPERTY.get(bill_type, 1)
    return _kit_met(status, material_property)


def _resolve_material_property(
    bill_type: Optional[int],
    po_summary,
    master: Optional[Material],
) -> Optional[int]:
    if bill_type is not None and bill_type in BILL_TYPE_TO_MATERIAL_PROPERTY:
        return BILL_TYPE_TO_MATERIAL_PROPERTY[bill_type]
    if po_summary and po_summary.material_property:
        return po_summary.material_property
    if master:
        if master.is_purchase:
            return 1
        if master.is_produce:
            return 2
    return None


def _allocate_stock(
    order_priority: list[str],
    plan_materials: dict[tuple[str, str], dict],
    po_groups: dict[tuple[str, str], dict],
    stock_by_material: dict[str, Decimal],
) -> dict[tuple[str, str], Decimal]:
    """按订单优先级分配物料级库存，返回每个 (order, material) 的可用库存。

    可用库存 = 该订单轮到自己时物料库存的剩余量（已被排在前面的订单按净需求占用）。
    净需求 = max(0, base_plan_qty - received_qty)。
    """
    available_map: dict[tuple[str, str], Decimal] = {}
    for (order_no, material_code), plan_info in plan_materials.items():
        # 仅对真实存在的物料做分配；先按物料分组初始化为 0
        available_map.setdefault((order_no, material_code), Decimal("0"))

    for material_code, total_stock in stock_by_material.items():
        remaining = total_stock if total_stock is not None else Decimal("0")
        for order_no in order_priority:
            key = (order_no, material_code)
            if key not in plan_materials:
                continue
            # 当前订单看到的可用库存 = 此时物料的剩余量
            available_map[key] = remaining
            # 占用净需求
            base_qty = plan_materials[key].get("base_plan_qty") or Decimal("0")
            po_info = po_groups.get(key)
            received = Decimal("0")
            if po_info and po_info.get("has_received_qty"):
                received = po_info["received_qty"] or Decimal("0")
            net_demand = base_qty - received
            if net_demand < 0:
                net_demand = Decimal("0")
            remaining = remaining - net_demand
            if remaining < 0:
                remaining = Decimal("0")
    return available_map


async def _get_stock_by_material(
    db: AsyncSession,
    material_codes: list[str],
) -> dict[str, Decimal]:
    """从 Inventory 表按物料编码汇总结存数量（所有仓库 + 库位汇总）。
    若 Inventory 表无数据，回退为 None（调用方使用 MrpPlanOrder.stock_qty 兜底）。
    """
    if not material_codes:
        return {}
    result = await db.execute(
        select(
            Inventory.material_code,
            func.sum(Inventory.balance_qty).label("total_balance"),
        )
        .where(Inventory.material_code.in_(material_codes))
        .group_by(Inventory.material_code)
    )
    stock_map: dict[str, Decimal] = {}
    for row in result:
        mc = row.material_code
        total = row.total_balance
        if mc and total is not None:
            stock_map[mc] = Decimal(str(total))
    return stock_map


def _order_priority_sort_key(order_no: str, promised_dates: dict[str, Optional[date]]) -> tuple:
    promised = promised_dates.get(order_no)
    # 交期为空排最后；同交期按订单号
    return (promised is None, promised or date.max, order_no)


async def _compute_available_stock_for_order(
    db: AsyncSession,
    target_order_no: str,
    material_codes: list[str],
) -> dict[str, Decimal]:
    """计算 target_order 各物料的可用库存（扣减其他订单按合同交期优先占用）。

    用于单订单物料明细场景：需查询涉及这些物料的所有订单，按交期分配库存。
    """
    if not material_codes:
        return {}

    # 1. 涉及这些物料的全部订单
    involved_result = await db.execute(
        select(MrpPlanOrder.sale_order_no)
        .where(MrpPlanOrder.material_code.in_(material_codes))
        .distinct()
    )
    involved_orders = sorted({r.sale_order_no for r in involved_result if r.sale_order_no})
    if not involved_orders:
        return {}

    # 2. 这些订单的合同交期（用于排序），并排除已关闭订单（与汇总口径一致）
    so_result = await db.execute(
        select(SaleOrder.order_no, SaleOrder.promised_date)
        .where(SaleOrder.order_no.in_(involved_orders), SaleOrder.is_closed == 0)
        .distinct()
    )
    promised: dict[str, Optional[date]] = {}
    open_orders: set[str] = set()
    for r in so_result:
        promised.setdefault(r.order_no, r.promised_date)
        open_orders.add(r.order_no)
    # 仅保留未关闭订单参与库存竞争；目标订单即便已关闭仍需展示自身明细
    active_orders = {o for o in involved_orders if o in open_orders or o == target_order_no}
    order_priority = sorted(
        active_orders,
        key=lambda o: _order_priority_sort_key(o, promised),
    )

    # 3. 这些订单对这些物料的需求 + 物料级库存
    plan_q = select(
        MrpPlanOrder.sale_order_no,
        MrpPlanOrder.material_code,
        MrpPlanOrder.base_plan_qty,
        MrpPlanOrder.stock_qty,
    ).where(
        MrpPlanOrder.sale_order_no.in_(active_orders),
        MrpPlanOrder.material_code.in_(material_codes),
    )
    plan_materials: dict[tuple[str, str], dict] = {}
    stock_by_material: dict[str, Decimal] = {}

    plan_result = await db.execute(plan_q)
    plan_rows = plan_result.all()

    # 填充 plan_materials（需求数据）
    for row in plan_rows:
        if not row.sale_order_no or not row.material_code:
            continue
        key = (row.sale_order_no, row.material_code)
        rec = plan_materials.setdefault(key, {"base_plan_qty": Decimal("0")})
        if row.base_plan_qty is not None:
            rec["base_plan_qty"] += row.base_plan_qty

    # 优先从 Inventory 表获取实时库存，Inventory 无该物料时按物料回退 MrpPlanOrder.stock_qty
    inv_stock = await _get_stock_by_material(db, material_codes)
    stock_by_material = dict(inv_stock)
    for row in plan_rows:
        if not row.sale_order_no or not row.material_code:
            continue
        if row.material_code in inv_stock:
            continue
        if row.stock_qty is not None:
            prev = stock_by_material.get(row.material_code)
            if prev is None or row.stock_qty > prev:
                stock_by_material[row.material_code] = row.stock_qty

    # 4. 收料聚合
    sync_filters = await get_purchase_order_sync_filters(db)
    po_q = select(
        PurchaseOrder.order_no,
        PurchaseOrder.material_code,
        PurchaseOrder.received_qty,
    ).where(
        PurchaseOrder.order_no.in_(active_orders),
        PurchaseOrder.material_code.in_(material_codes),
        *sync_filters,
    )
    po_received: dict[tuple[str, str], Decimal] = {}
    for row in await db.execute(po_q):
        if not row.order_no or not row.material_code:
            continue
        key = (row.order_no, row.material_code)
        po_received[key] = po_received.get(key, Decimal("0")) + (row.received_qty or Decimal("0"))

    po_groups: dict[tuple[str, str], dict] = {}
    for key, recv in po_received.items():
        po_groups[key] = {"received_qty": recv, "has_received_qty": True}

    # 5. 分配
    available_map = _allocate_stock(order_priority, plan_materials, po_groups, stock_by_material)
    return {
        mat: available_map.get((target_order_no, mat), Decimal("0"))
        for mat in material_codes
    }


async def _get_bom_demand_map(
    db: AsyncSession,
    order_no: str,
) -> tuple[dict[str, Decimal], dict[str, tuple[str, str]]]:
    """通过 SaleOrderLine → BomDetail → Material 计算各物料的 BOM 需求量与归属产品。

    递归展开多层 BOM：若 BomDetail 中的子件物料本身有子 BOM（scm_bom 中存在该 material_id 的记录），
    则继续往下展开，将所有层级的物料拆解成列表放到同一层。
    需求量 = 本级 standard_qty × 上级需求量，跨多行聚合求和；子级除以 base_qty 换算。
    返回 (demand_map, product_map)，其中：
      demand_map:  dict[material_code -> bom_demand_qty]
      product_map: dict[material_code -> (product_code, product_name)]
    """
    # 1. 查询销售订单明细行
    line_result = await db.execute(
        select(SaleOrderLine)
        .where(SaleOrderLine.order_no == order_no)
    )
    lines = line_result.scalars().all()
    if not lines:
        return {}, {}

    # 2. 构建根 BOM 需求量与归属产品
    root_bom_demands: dict[str, Decimal] = {}
    root_products: dict[str, tuple[str, str]] = {}
    for line in lines:
        bom_id = str(line.bom_id) if getattr(line, "bom_id", None) else None
        if not bom_id:
            continue
        order_qty = line.order_qty if line.order_qty is not None else Decimal("0")
        root_bom_demands[bom_id] = root_bom_demands.get(bom_id, Decimal("0")) + order_qty
        if bom_id not in root_products:
            root_products[bom_id] = (line.product_code or "", line.product_name or "")
    if not root_bom_demands:
        return {}, {}

    # 3. BFS 逐层展开
    demand: dict[str, Decimal] = {}
    product: dict[str, tuple[str, str]] = {}
    visited_bom_ids: set[str] = set()
    material_map: dict[str, Material] = {}
    # queue: [(bom_id, demand_factor, product_info)]
    queue: list[tuple[str, Decimal, tuple[str, str]]] = [
        (bid, demand_factor, root_products.get(bid, ("", "")))
        for bid, demand_factor in root_bom_demands.items()
    ]

    while queue:
        level_bom_ids = {bid for bid, _, _ in queue if bid not in visited_bom_ids}
        if not level_bom_ids:
            break
        visited_bom_ids.update(level_bom_ids)

        # 查询当前层级的 BomDetail
        detail_result = await db.execute(
            select(BomDetail).where(BomDetail.bom_id.in_(level_bom_ids))
        )
        details_list = detail_result.scalars().all()

        # 按 bom_id 分组，同时收集子物料 ID
        bom_detail_map: dict[str, list[tuple[int, Decimal]]] = {}
        child_material_ids: set[int] = set()
        for d in details_list:
            if d.material_id and d.standard_qty is not None:
                bom_detail_map.setdefault(d.bom_id, []).append((d.material_id, d.standard_qty))
                child_material_ids.add(d.material_id)

        if not child_material_ids:
            break

        # 查询新出现的 Material 主数据
        new_material_ids = child_material_ids - set(material_map.keys())
        if new_material_ids:
            mat_result = await db.execute(
                select(Material).where(Material.erp_material_id.in_(new_material_ids))
            )
            for m in mat_result.scalars().all():
                material_map[m.erp_material_id] = m

        # 查询子物料中哪些有子 BOM
        sub_material_boms: dict[int, Bom] = {}
        bom_result = await db.execute(
            select(Bom).where(Bom.material_id.in_(child_material_ids))
        )
        for b in bom_result.scalars().all():
            sub_material_boms[b.material_id] = b

        # 计算本级需求量，并构建下一层级队列
        next_queue: list[tuple[str, Decimal, tuple[str, str]]] = []
        for bom_id, demand_factor, product_info in queue:
            if bom_id not in bom_detail_map:
                continue
            for material_id, standard_qty in bom_detail_map[bom_id]:
                master = material_map.get(material_id)
                if not master:
                    continue
                material_code = master.material_code
                material_demand = standard_qty * demand_factor
                demand[material_code] = demand.get(material_code, Decimal("0")) + material_demand
                if material_code not in product:
                    product[material_code] = product_info

                # 检查子物料是否有子 BOM，有则入队继续展开
                sub_bom = sub_material_boms.get(material_id)
                if sub_bom and sub_bom.bom_id not in visited_bom_ids:
                    base_qty = sub_bom.base_qty if sub_bom.base_qty else Decimal("1")
                    next_queue.append((sub_bom.bom_id, material_demand / base_qty, product_info))

        queue = next_queue

    return demand, product


async def _get_plan_order_material_items(
    db: AsyncSession,
    order_no: str,
) -> list[KitAnalysisMaterialItem]:
    """以 mrp_plan_order 为数据源构建订单物料明细，并按 sale_order_no+material_code 关联采购订单。"""
    plan_result = await db.execute(
        select(MrpPlanOrder)
        .where(MrpPlanOrder.sale_order_no == order_no)
        .order_by(MrpPlanOrder.material_code)
    )
    plans = plan_result.scalars().all()

    material_codes = sorted({p.material_code for p in plans if p.material_code})

    master_map: dict[str, Material] = {}
    if material_codes:
        master_result = await db.execute(
            select(Material).where(Material.material_code.in_(material_codes))
        )
        master_map = {m.material_code: m for m in master_result.scalars().all()}

    # 从 Inventory 表获取实时库存（回退到 MrpPlanOrder.stock_qty）
    inv_stock_map = await _get_stock_by_material(db, material_codes)

    po_map: dict[str, list[PurchaseOrder]] = {}
    if material_codes:
        sync_filters = await get_purchase_order_sync_filters(db)
        po_result = await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.order_no == order_no,
                PurchaseOrder.material_code.in_(material_codes),
                *sync_filters,
            )
        )
        for po in po_result.scalars().all():
            po_map.setdefault(po.material_code, []).append(po)

    # 跨订单库存分配：扣减其他订单（按合同交期优先）占用后的可用库存
    available_stock_map = await _compute_available_stock_for_order(db, order_no, material_codes)

    # BOM需求量：通过 SaleOrderLine → BomDetail → Material 计算
    bom_demand_map, product_map = await _get_bom_demand_map(db, order_no)

    items: list[KitAnalysisMaterialItem] = []
    for plan in plans:
        if not plan.material_code:
            continue
        base_qty = plan.base_plan_qty or Decimal("0")
        # MRP数量为0的物料不展开
        if base_qty == 0:
            continue
        pos = po_map.get(plan.material_code, [])
        po_summary = _summarize_pos(pos)
        bill_type = plan.bill_type
        master = master_map.get(plan.material_code)
        # 物料属性优先取计划订单自身的字段（来源 K3 FErpClsID），缺失时回退推导
        material_property = plan.material_property
        if material_property is None:
            material_property = _resolve_material_property(bill_type, po_summary, master)
        status = _status_for_plan(bill_type, po_summary)

        received_qty = po_summary.received_qty if po_summary else None
        po_qty = po_summary.po_qty if po_summary else None
        stagnant_qty = (
            received_qty - po_qty
            if received_qty is not None and po_qty is not None and received_qty > po_qty
            else None
        )

        # 库存满足净需求时视作已到齐，与汇总口径保持一致
        # 净需求 = 需求量 - 已收料；自制(2)/配置类(7)不参与齐套统计
        received_for_net = received_qty if received_qty is not None else Decimal("0")
        net_demand = base_qty - received_for_net
        if net_demand < 0:
            net_demand = Decimal("0")
        available_stock = available_stock_map.get(plan.material_code) or Decimal("0")
        stock_met = (
            net_demand > 0
            and available_stock >= net_demand
            and material_property not in (2, 7)
        )
        if stock_met and status != "fully_received":
            status = "fully_received"
        # 库存 >= MRP数量 且无对应订单时，状态显示"有库存"并记入齐套
        stock_qty_val = inv_stock_map.get(plan.material_code) or plan.stock_qty or Decimal("0")
        if stock_qty_val >= base_qty and not pos:
            status = "in_stock"
        material_type = plan.material_type
        material_name = (
            plan.material_name
            or (po_summary.material_name if po_summary else None)
            or (master.material_name if master else None)
        )

        items.append(KitAnalysisMaterialItem(
            material_code=plan.material_code,
            material_name=material_name,
            product_code=product_map.get(plan.material_code, (None, None))[0] or None,
            product_name=product_map.get(plan.material_code, (None, None))[1] or None,
            material_property=material_property,
            material_property_label=_material_property_label(material_property),
            material_type=material_type,
            unit_name=plan.unit_name,
            supplier_name=po_summary.supplier_name if po_summary else None,
            order_qty=_to_float(plan.base_plan_qty),
            mrp_qty=_to_float(plan.base_plan_qty),
            po_qty=_to_float(po_qty),
            stock_qty=_to_float(inv_stock_map.get(plan.material_code) or plan.stock_qty),
            available_stock_qty=_to_float(available_stock_map.get(plan.material_code)),
            shortage_qty=(
                _to_float(po_qty - received_qty)
                if po_qty is not None and received_qty is not None and po_qty > received_qty
                else None
            ),
            req_date=plan.need_date,
            po_no=po_summary.po_no if po_summary else None,
            po_count=po_summary.po_count if po_summary else 0,
            received_qty=_to_float(received_qty),
            eta=po_summary.eta if po_summary else None,
            first_eta=po_summary.first_eta if po_summary else None,
            latest_eta=po_summary.latest_eta if po_summary else None,
            actual_arrival_date=po_summary.actual_arrival_date if po_summary else None,
            inspection_date=po_summary.inspection_date if po_summary else None,
            status=status,
            status_label=STATUS_LABELS.get(status, status),
            is_stagnant=stagnant_qty is not None,
            stagnant_qty=_to_float(stagnant_qty),
            is_closed=po_summary.is_closed if po_summary else 0,
            bill_type=bill_type,
            bill_type_label=BILL_TYPE_LABELS.get(bill_type),
            bom_demand_qty=_to_float(bom_demand_map.get(plan.material_code)),
            transit_qty=_to_float(
                po_qty - received_qty
                if po_qty is not None and received_qty is not None and po_qty > received_qty
                else (po_qty if po_qty is not None and po_qty > 0 else None)
            ),
        ))

    return items


async def get_kit_analysis(
    db: AsyncSession,
    order_no: Optional[str] = None,
    order_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    only_pending_shipment: bool = False,
    promised_date_start: Optional[str] = None,
    promised_date_end: Optional[str] = None,
) -> dict:
    """按销售订单汇总物料齐套状态（基于销售订单表查询），外层列表保持按销售订单展示。"""
    # 1. 从销售订单表获取订单列表
    sale_order_query = select(
        SaleOrder.order_no,
        SaleOrder.promised_date,
        SaleOrder.delivery_completed_date,
        SaleOrder.is_closed,
    ).distinct().where(SaleOrder.order_no.is_not(None))

    if order_no:
        sale_order_query = sale_order_query.where(SaleOrder.order_no.ilike(f"%{order_no}%"))
    if order_type:
        types = [x.strip() for x in order_type.split(',') if x.strip()]
        if types:
            type_filters = []
            for t in types:
                if t == 'big':
                    type_filters.append(SaleOrder.order_no.ilike('HJ%') & ~SaleOrder.order_no.ilike('HJY%'))
                elif t == 'sample':
                    type_filters.append(SaleOrder.order_no.ilike('HJY%'))
            if type_filters:
                if len(type_filters) == 1:
                    sale_order_query = sale_order_query.where(type_filters[0])
                else:
                    sale_order_query = sale_order_query.where(or_(*type_filters))
    if only_pending_shipment:
        sale_order_query = sale_order_query.where(SaleOrder.delivery_completed_date.is_(None))
    if promised_date_start:
        sale_order_query = sale_order_query.where(SaleOrder.promised_date >= date.fromisoformat(promised_date_start))
    if promised_date_end:
        sale_order_query = sale_order_query.where(SaleOrder.promised_date <= date.fromisoformat(promised_date_end))
    sale_order_query = sale_order_query.where(SaleOrder.is_closed == 0)

    sale_order_result = await db.execute(sale_order_query)
    sale_order_rows = sale_order_result.all()

    order_nos = sorted({row.order_no for row in sale_order_rows if row.order_no})
    promised_dates: dict[str, date | None] = {}
    pending_shipment_orders: set[str] = set()
    for row in sale_order_rows:
        promised_dates.setdefault(row.order_no, row.promised_date)
        if row.delivery_completed_date is None:
            pending_shipment_orders.add(row.order_no)

    # 2. 从 MRP 计划订单获取对应订单的物料清单
    plan_materials: dict[tuple[str, str], dict] = {}
    stock_by_material: dict[str, Decimal] = {}
    # 「有库存」判定库存（与明细口径一致：Inventory 可用量为 0/缺失时回退 MRP 快照库存）
    in_stock_qty_by_material: dict[str, Decimal] = {}
    material_codes: list[str] = []
    if order_nos:
        plan_query = select(
            MrpPlanOrder.sale_order_no,
            MrpPlanOrder.material_code,
            MrpPlanOrder.base_plan_qty,
            MrpPlanOrder.bill_type,
            MrpPlanOrder.material_property,
            MrpPlanOrder.need_date,
            MrpPlanOrder.is_closed,
            MrpPlanOrder.stock_qty,
        ).where(MrpPlanOrder.sale_order_no.in_(order_nos))
        plan_result = await db.execute(plan_query)
        plan_rows = plan_result.all()
        for row in plan_rows:
            if not row.sale_order_no or not row.material_code:
                continue
            if row.base_plan_qty is None or row.base_plan_qty == 0:
                continue
            key = (row.sale_order_no, row.material_code)
            if key not in plan_materials:
                plan_materials[key] = {
                    "base_plan_qty": Decimal("0"),
                    "bill_type": row.bill_type,
                    "material_property": row.material_property,
                    "need_date": row.need_date,
                    "is_closed": row.is_closed,
                }
            if row.base_plan_qty is not None:
                plan_materials[key]["base_plan_qty"] += row.base_plan_qty

        material_codes = sorted({mat_code for _, mat_code in plan_materials})

        # MRP 快照库存（按物料取最大值），用于 Inventory 无实时数据时回退
        plan_stock_by_material: dict[str, Decimal] = {}
        for row in plan_rows:
            if not row.material_code or row.stock_qty is None:
                continue
            prev = plan_stock_by_material.get(row.material_code)
            if prev is None or row.stock_qty > prev:
                plan_stock_by_material[row.material_code] = row.stock_qty

        # 库存分配基准：优先 Inventory 实时可用量，Inventory 无该物料时回退 MRP 快照库存
        inv_stock = await _get_stock_by_material(db, material_codes)
        stock_by_material = dict(inv_stock)
        for mat_code, snapshot_qty in plan_stock_by_material.items():
            if mat_code not in inv_stock:
                stock_by_material[mat_code] = snapshot_qty

        # 「有库存」判定库存：与明细 inv_stock_map.get(code) or plan.stock_qty 完全一致
        # （Inventory 可用量为 0 时同样回退 MRP 快照库存，确保有库存物料计入已到齐）
        in_stock_qty_by_material = {
            mat_code: (inv_stock.get(mat_code) or plan_stock_by_material.get(mat_code) or Decimal("0"))
            for mat_code in material_codes
        }

    # 3. 从采购订单获取对应物料的采购/收料数据
    sync_filters = await get_purchase_order_sync_filters(db)
    po_groups: dict[tuple[str, str], dict] = {}
    if order_nos and material_codes:
        po_query = select(
            PurchaseOrder.order_no,
            PurchaseOrder.material_code,
            PurchaseOrder.po_qty,
            PurchaseOrder.received_qty,
            PurchaseOrder.eta,
            PurchaseOrder.actual_arrival_date,
            PurchaseOrder.inspection_date,
            PurchaseOrder.is_closed,
        ).where(
            PurchaseOrder.order_no.in_(order_nos),
            PurchaseOrder.material_code.in_(material_codes),
            *sync_filters,
        )
        po_result = await db.execute(po_query)
        for row in po_result:
            if not row.order_no or not row.material_code:
                continue
            key = (row.order_no, row.material_code)
            group = po_groups.setdefault(
                key,
                {
                    "po_qty": Decimal("0"),
                    "has_po_qty": False,
                    "received_qty": Decimal("0"),
                    "has_received_qty": False,
                    "eta": None,
                    "actual_arrival_date": None,
                    "inspection_date": None,
                    "is_closed": 0,
                    "po_count": 0,
                },
            )
            group["po_count"] += 1
            if row.po_qty is not None:
                group["po_qty"] += row.po_qty
                group["has_po_qty"] = True
            if row.received_qty is not None:
                group["received_qty"] += row.received_qty
                group["has_received_qty"] = True
            if row.eta and (group["eta"] is None or row.eta < group["eta"]):
                group["eta"] = row.eta
            if row.actual_arrival_date and (
                group["actual_arrival_date"] is None
                or row.actual_arrival_date > group["actual_arrival_date"]
            ):
                group["actual_arrival_date"] = row.actual_arrival_date
            if row.inspection_date and (
                group["inspection_date"] is None
                or row.inspection_date > group["inspection_date"]
            ):
                group["inspection_date"] = row.inspection_date
            if row.is_closed and row.is_closed == 1:
                group["is_closed"] = 1

    # 4. 按合同交期计算订单优先级，分配物料级库存得到每个 (order,material) 的可用库存
    order_priority = sorted(
        order_nos,
        key=lambda o: _order_priority_sort_key(o, promised_dates),
    )
    available_map = _allocate_stock(order_priority, plan_materials, po_groups, stock_by_material)

    # 5. 按销售订单计算齐套指标
    items: List[KitAnalysisItem] = []
    per_order_materials: dict[str, list[tuple[str, dict]]] = {}
    for (sale_order_no, material_code), plan_info in plan_materials.items():
        per_order_materials.setdefault(sale_order_no, []).append((material_code, plan_info))

    for current_order_no in order_nos:
        order_mat_list = per_order_materials.get(current_order_no, [])
        total = len(order_mat_list)
        received_count = 0
        partial_count = 0
        not_ordered_count = 0
        overdue_count = 0
        stagnant_count = 0

        for material_code, plan_info in order_mat_list:
            po_info = po_groups.get((current_order_no, material_code))
            bill_type = plan_info.get("bill_type")
            material_property = plan_info.get("material_property")
            po_summary = None
            if po_info:
                po_summary = SimpleNamespace(
                    po_qty=po_info["po_qty"] if po_info["has_po_qty"] else None,
                    received_qty=po_info["received_qty"] if po_info["has_received_qty"] else None,
                    eta=po_info["eta"],
                    actual_arrival_date=po_info["actual_arrival_date"],
                    inspection_date=po_info["inspection_date"],
                    is_closed=po_info.get("is_closed", 0),
                    material_property=material_property,
                    supplier_name=None,
                    po_no=None,
                    po_count=po_info.get("po_count", 0),
                    first_eta=None,
                    latest_eta=None,
                )

            status = _status_for_plan(bill_type, po_summary)
            kit_met = _kit_met_for_plan(status, bill_type)

            has_po = po_info and po_info["has_po_qty"] and po_info["po_qty"] > 0
            has_received = po_info and po_info["has_received_qty"] and po_info["received_qty"] > 0
            fully_received = has_po and has_received and po_info["received_qty"] >= po_info["po_qty"]
            partial_received = has_received and (not has_po or po_info["received_qty"] < po_info["po_qty"])

            # 库存满足：可用库存 ≥ 净需求(需求 - 已收料)，且净需求 > 0
            base_qty = plan_info.get("base_plan_qty") or Decimal("0")
            received_for_net = po_info["received_qty"] if (po_info and po_info.get("has_received_qty")) else Decimal("0")
            net_demand = base_qty - received_for_net
            if net_demand < 0:
                net_demand = Decimal("0")
            available = available_map.get((current_order_no, material_code), Decimal("0"))
            stock_met = net_demand > 0 and available >= net_demand

            # 「有库存」状态：库存 >= MRP数量 且无对应采购订单（与明细口径一致）
            stock_qty_for_mat = in_stock_qty_by_material.get(material_code) or Decimal("0")
            in_stock = stock_qty_for_mat >= base_qty and not po_info

            # 已到齐 — 自制、配置类不参与齐套统计（有库存/库存覆盖除外）
            # 「有库存」状态的物料同样按已齐套计算
            material_prop = material_property if material_property is not None else BILL_TYPE_TO_MATERIAL_PROPERTY.get(bill_type)
            if (material_prop not in (2, 7) and (kit_met or fully_received or stock_met)) or in_stock:
                received_count += 1
            # 部分到
            elif partial_received:
                partial_count += 1
            # 未下单
            elif not has_po and status in ("not_ordered", "not_scheduled"):
                not_ordered_count += 1

            # 逾期：有 PO 且 ETA 早于今天但未到齐、库存也不满足
            if po_info and po_info.get("eta") and po_info["eta"] < date.today():
                if not fully_received and not kit_met and not stock_met and not in_stock:
                    overdue_count += 1

            # 呆滞：收料数量 > 下单数量
            if (
                po_info
                and po_info["has_po_qty"]
                and po_info["has_received_qty"]
                and po_info["received_qty"] > po_info["po_qty"]
            ):
                stagnant_count += 1

        # 齐套率 = 已到齐物料数 / 总物料数
        kit_rate = round(received_count / total, 4) if total else 0
        current_risk_level = _kit_risk_level(kit_rate)
        if risk_level and current_risk_level != risk_level:
            continue

        items.append(KitAnalysisItem(
            order_no=current_order_no,
            total_materials=total,
            received_materials=received_count,
            partial_received_materials=partial_count,
            not_ordered_materials=not_ordered_count,
            overdue_materials=overdue_count,
            stagnant_materials=stagnant_count,
            kit_rate=kit_rate,
            risk_level=current_risk_level,
            promised_date=promised_dates.get(current_order_no),
        ))

    if sort_by and sort_by in KIT_SORT_KEYS:
        reverse = sort_order == "desc"

        def sort_key(item):
            value = getattr(item, sort_by, None)
            if value is None:
                return (True, 0)
            return (False, value)

        items.sort(key=sort_key, reverse=reverse)
    else:
        items.sort(key=lambda item: item.kit_rate)

    total_count = len(items)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_items = items[start_idx:end_idx]

    return {
        "items": paginated_items,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "statistics": {
            "red_count": sum(1 for item in items if item.risk_level == "red"),
            "yellow_count": sum(1 for item in items if item.risk_level == "yellow"),
            "green_count": sum(1 for item in items if item.risk_level == "green"),
            "avg_kit_rate": round(sum(item.kit_rate for item in items) / len(items) * 100) if items else 0,
        },
    }


async def get_order_materials(
    db: AsyncSession,
    order_no: str,
    material_code_filter: Optional[str] = None,
    material_name_filter: Optional[str] = None,
    material_property_filter: Optional[str] = None,
    material_type_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    supplier_filter: Optional[str] = None,
    po_qty_min: Optional[float] = None,
    po_qty_max: Optional[float] = None,
    received_qty_min: Optional[float] = None,
    received_qty_max: Optional[float] = None,
    eta_start: Optional[str] = None,
    eta_end: Optional[str] = None,
    actual_arrival_date_start: Optional[str] = None,
    actual_arrival_date_end: Optional[str] = None,
    inspection_date_start: Optional[str] = None,
    inspection_date_end: Optional[str] = None,
    is_stagnant: Optional[bool] = None,
    bill_type_filter: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> List[KitAnalysisMaterialItem]:
    """展开订单后的物料明细，基于 MRP 计划订单，关联采购订单推导状态。"""
    items = await _get_plan_order_material_items(db, order_no)

    # 已关闭的物料，已到齐/部分到仍返回，其他状态不返回
    items = [item for item in items if not (item.is_closed == 1 and item.status not in ("partial_received", "fully_received"))]

    if material_code_filter:
        needle = material_code_filter.lower()
        items = [item for item in items if needle in item.material_code.lower()]
    if material_name_filter:
        needle = material_name_filter.lower()
        items = [item for item in items if item.material_name and needle in item.material_name.lower()]
    if material_property_filter:
        property_values = {int(value.strip()) for value in material_property_filter.split(",") if value.strip()}
        items = [item for item in items if item.material_property in property_values]
    if material_type_filter:
        needle = material_type_filter.lower()
        items = [item for item in items if item.material_type and needle in item.material_type.lower()]
    if supplier_filter:
        needle = supplier_filter.lower()
        items = [item for item in items if item.supplier_name and needle in item.supplier_name.lower()]
    if po_qty_min is not None:
        items = [item for item in items if item.po_qty is not None and item.po_qty >= po_qty_min]
    if po_qty_max is not None:
        items = [item for item in items if item.po_qty is not None and item.po_qty <= po_qty_max]
    if received_qty_min is not None:
        items = [item for item in items if item.received_qty is not None and item.received_qty >= received_qty_min]
    if received_qty_max is not None:
        items = [item for item in items if item.received_qty is not None and item.received_qty <= received_qty_max]
    if eta_start:
        start = date.fromisoformat(eta_start)
        items = [item for item in items if item.eta is not None and item.eta >= start]
    if eta_end:
        end = date.fromisoformat(eta_end)
        items = [item for item in items if item.eta is not None and item.eta <= end]
    if actual_arrival_date_start:
        start = date.fromisoformat(actual_arrival_date_start)
        items = [item for item in items if item.actual_arrival_date is not None and item.actual_arrival_date >= start]
    if actual_arrival_date_end:
        end = date.fromisoformat(actual_arrival_date_end)
        items = [item for item in items if item.actual_arrival_date is not None and item.actual_arrival_date <= end]
    if inspection_date_start:
        start = date.fromisoformat(inspection_date_start)
        items = [item for item in items if item.inspection_date is not None and item.inspection_date >= start]
    if inspection_date_end:
        end = date.fromisoformat(inspection_date_end)
        items = [item for item in items if item.inspection_date is not None and item.inspection_date <= end]
    if is_stagnant is True:
        items = [item for item in items if item.is_stagnant]
    elif is_stagnant is False:
        items = [item for item in items if not item.is_stagnant]
    if bill_type_filter:
        bill_types = {int(value.strip()) for value in bill_type_filter.split(",") if value.strip()}
        items = [item for item in items if item.bill_type in bill_types]

    if status_filter:
        statuses = {status.strip() for status in status_filter.split(",") if status.strip()}
        items = [item for item in items if item.status in statuses]

    if sort_by and sort_by in MATERIAL_SORT_KEYS:
        reverse = sort_order == "desc"

        def sort_key(item):
            value = getattr(item, sort_by, None)
            if value is None:
                return (True, 0)
            return (False, value)

        items.sort(key=sort_key, reverse=reverse)

    return items


async def get_order_product_breakdown(
    db: AsyncSession,
    order_no: str,
) -> dict:
    """按订单下产品 + BOM 多级树返回齐套明细。

    一次返回:
      - products: 产品列表(每产品含汇总状态)
      - bom_trees: {product_key: BOM 树},树节点含订单级齐套数字
      - orphan_materials: MrpPlanOrder 中存在但 BOM 未覆盖的物料
    """
    from decimal import Decimal as _Decimal
    from collections import defaultdict

    line_result = await db.execute(
        select(SaleOrderLine)
        .where(SaleOrderLine.order_no == order_no)
        .order_by(SaleOrderLine.id)
    )
    lines = line_result.scalars().all()

    if not lines:
        order_q = await db.execute(select(SaleOrder).where(SaleOrder.order_no == order_no))
        order = order_q.scalar_one_or_none()
        if order:
            lines = [SimpleNamespace(
                order_no=order.order_no,
                line_no=order.line_no,
                product_code=order.product_code,
                product_name=order.product_name,
                product_model=None,
                order_qty=order.order_qty,
                promised_date=order.promised_date,
                bom_id=None,
                bom_no=None,
            )]

    # 1) 订单级齐套数字(扁平),按 material_code 索引
    order_materials = await get_order_materials(db, order_no=order_no)
    mat_by_code: dict[str, KitAnalysisMaterialItem] = {m.material_code: m for m in order_materials}

    # 2) 按 (product_code, bom_id) 分组产品行
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for line in lines:
        line_bom_id = str(line.bom_id) if getattr(line, "bom_id", None) else None
        key = (line.product_code or "", line_bom_id or "")
        groups[key].append(line)

    products: list[ProductKitSummary] = []
    bom_trees: dict[str, list[BomKitMaterialItem]] = {}
    covered_codes: set[str] = set()

    for idx, ((product_code_key, bom_id_key), group_lines) in enumerate(groups.items()):
        first = group_lines[0]
        total_qty = _Decimal("0")
        line_nos: list[str] = []
        promised = None
        for ln in group_lines:
            qty = ln.order_qty if ln.order_qty is not None else 0
            total_qty += _Decimal(str(qty))
            if ln.line_no is not None:
                line_nos.append(str(ln.line_no))
            pd_ = ln.promised_date
            if pd_ is not None and (promised is None or pd_ < promised):
                promised = pd_
        merged_bom_id = bom_id_key or None

        product_key = f"{product_code_key}#{idx}"

        if merged_bom_id:
            tree_nodes = await _expand_bom_tree(db, merged_bom_id, total_qty)
        else:
            tree_nodes = []

        kit_tree = _attach_kit_to_tree(tree_nodes, mat_by_code, covered_codes)

        # 产品级汇总:按 material_code 去重计数
        per_product_counts: dict[str, KitAnalysisMaterialItem] = {}
        _collect_unique_materials(kit_tree, mat_by_code, per_product_counts)

        leaf_total = len(per_product_counts)
        leaf_received = sum(1 for m in per_product_counts.values() if m.status == "fully_received")
        leaf_partial = sum(1 for m in per_product_counts.values() if m.status == "partial_received")
        leaf_not_ordered = sum(1 for m in per_product_counts.values() if m.status in ("not_ordered", "self_made_unlinked"))
        leaf_overdue = sum(1 for m in per_product_counts.values() if m.status == "overdue")
        leaf_stagnant = sum(1 for m in per_product_counts.values() if m.is_stagnant)
        kit_rate = (leaf_received / leaf_total) if leaf_total else 0.0
        risk = _kit_risk_level(kit_rate)

        products.append(ProductKitSummary(
            line_no=",".join(line_nos) if line_nos else None,
            product_code=first.product_code,
            product_name=first.product_name,
            product_model=getattr(first, "product_model", None),
            bom_no=getattr(first, "bom_no", None),
            bom_id=merged_bom_id,
            order_qty=_to_float(total_qty),
            promised_date=promised,
            leaf_total=leaf_total,
            leaf_received=leaf_received,
            leaf_partial=leaf_partial,
            leaf_not_ordered=leaf_not_ordered,
            leaf_overdue=leaf_overdue,
            leaf_stagnant=leaf_stagnant,
            has_bom=bool(merged_bom_id),
            kit_rate=kit_rate,
            risk_level=risk,
        ))
        bom_trees[product_key] = kit_tree

    # 3) 孤儿物料 = 订单级物料中,material_code 不在任何产品 BOM 树里
    orphan_materials = [m for code, m in mat_by_code.items() if code not in covered_codes]

    return OrderProductKitBreakdownOut(
        order_no=order_no,
        products=products,
        orphan_materials=orphan_materials,
        bom_trees=bom_trees,
    ).model_dump()


def _attach_kit_to_tree(
    nodes: list,
    mat_by_code: dict[str, KitAnalysisMaterialItem],
    covered_codes: set[str],
) -> list[BomKitMaterialItem]:
    """把 BomDetailItemOut 节点转成 BomKitMaterialItem,并按 material_code 关联订单级齐套数字。"""
    result: list[BomKitMaterialItem] = []
    for node in nodes:
        code = node.material_code
        kit_item = mat_by_code.get(code) if code else None
        if code:
            covered_codes.add(code)
        base_data = kit_item.model_dump() if kit_item else {}
        base_data.update({
            "level": node.level,
            "bom_id": node.bom_id,
            "standard_qty": node.standard_qty,
            "req_qty": node.req_qty,
            "has_sub_bom": node.has_sub_bom,
            "children": _attach_kit_to_tree(node.children, mat_by_code, covered_codes),
        })
        if not kit_item:
            # BOM 有但 MrpPlanOrder 没记录 → 清掉必填字段的占位
            base_data["material_code"] = code or ""
            base_data["status"] = "not_in_plan"
            base_data.setdefault("status_label", None)
        result.append(BomKitMaterialItem(**base_data))
    return result


def _collect_unique_materials(
    nodes: list,
    mat_by_code: dict[str, KitAnalysisMaterialItem],
    out: dict[str, KitAnalysisMaterialItem],
) -> None:
    """DFS 收集树中所有出现在 mat_by_code 的 material_code(去重)。"""
    for node in nodes:
        code = getattr(node, "material_code", None)
        if code and code in mat_by_code and code not in out:
            out[code] = mat_by_code[code]
        children = getattr(node, "children", []) or []
        if children:
            _collect_unique_materials(children, mat_by_code, out)
