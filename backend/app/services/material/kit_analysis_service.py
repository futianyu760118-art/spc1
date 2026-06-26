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
from app.models.material.mrp_plan_order import MrpPlanOrder
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.sale_order import SaleOrder
from app.schemas.material.schemas import KitAnalysisItem, KitAnalysisMaterialItem
from app.services.common.sync_filter import get_purchase_order_sync_filters
# 复用订单物料服务中的状态推断与 PO 汇总逻辑，保证齐套口径一致
from app.services.order.order_materials_service import (
    STATUS_LABELS,
    _kit_met,
    _material_property_label,
    _status,
    _summarize_pos,
    _to_float,
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

    items: list[KitAnalysisMaterialItem] = []
    for plan in plans:
        if not plan.material_code:
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
        material_type = plan.material_type
        material_name = (
            plan.material_name
            or (po_summary.material_name if po_summary else None)
            or (master.material_name if master else None)
        )

        items.append(KitAnalysisMaterialItem(
            material_code=plan.material_code,
            material_name=material_name,
            material_property=material_property,
            material_property_label=_material_property_label(material_property),
            material_type=material_type,
            unit_name=plan.unit_name,
            supplier_name=po_summary.supplier_name if po_summary else None,
            order_qty=_to_float(plan.base_plan_qty),
            mrp_qty=_to_float(plan.base_plan_qty),
            po_qty=_to_float(po_qty),
            stock_qty=_to_float(plan.stock_qty),
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
    if order_nos:
        plan_query = select(
            MrpPlanOrder.sale_order_no,
            MrpPlanOrder.material_code,
            MrpPlanOrder.base_plan_qty,
            MrpPlanOrder.bill_type,
            MrpPlanOrder.material_property,
            MrpPlanOrder.need_date,
            MrpPlanOrder.is_closed,
        ).where(MrpPlanOrder.sale_order_no.in_(order_nos))
        plan_result = await db.execute(plan_query)
        for row in plan_result:
            if not row.sale_order_no or not row.material_code:
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

    # 3. 从采购订单获取对应物料的采购/收料数据
    sync_filters = await get_purchase_order_sync_filters(db)
    material_codes = sorted({mat_code for _, mat_code in plan_materials})
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
                },
            )
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

    # 4. 按销售订单计算齐套指标
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
                    po_count=0,
                    first_eta=None,
                    latest_eta=None,
                )

            status = _status_for_plan(bill_type, po_summary)
            kit_met = _kit_met_for_plan(status, bill_type)

            has_po = po_info and po_info["has_po_qty"] and po_info["po_qty"] > 0
            has_received = po_info and po_info["has_received_qty"] and po_info["received_qty"] > 0
            fully_received = has_po and has_received and po_info["received_qty"] >= po_info["po_qty"]
            partial_received = has_received and (not has_po or po_info["received_qty"] < po_info["po_qty"])

            # 已到齐
            if kit_met or fully_received:
                received_count += 1
            # 部分到
            elif partial_received:
                partial_count += 1
            # 未下单
            elif not has_po and status in ("not_ordered", "not_scheduled"):
                not_ordered_count += 1

            # 逾期：有 PO 且 ETA 早于今天但未到齐
            if po_info and po_info.get("eta") and po_info["eta"] < date.today():
                if not fully_received and not kit_met:
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
