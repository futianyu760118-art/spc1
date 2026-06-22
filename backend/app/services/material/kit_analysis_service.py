"""Material kit analysis service."""

from datetime import date
from typing import Optional, List

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.material_demand import MaterialDemand
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.sale_order import SaleOrder
from app.schemas.material.schemas import KitAnalysisItem, KitAnalysisMaterialItem
from app.services.order.order_materials_service import get_order_product_materials
from app.services.common.sync_filter import get_purchase_order_sync_filters


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
    "order_qty",
    "received_qty",
    "eta",
    "actual_arrival_date",
    "inspection_date",
    "status",
    "is_stagnant",
}


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _sum_decimal(values) -> Optional[Decimal]:
    total = Decimal("0")
    seen = False
    for value in values:
        if value is not None:
            total += value
            seen = True
    return total if seen else None


def _pick_first(values):
    return next((value for value in values if value not in (None, "")), None)


def _po_status(po_group: list[PurchaseOrder]) -> str:
    received_qty = _sum_decimal([po.received_qty for po in po_group])
    po_qty = _sum_decimal([po.po_qty for po in po_group])
    # 状态纯按收料数量推导（已到料状态已移除）
    if received_qty is not None and received_qty > 0:
        if po_qty is not None and received_qty >= po_qty:
            return "fully_received"
        return "partial_received"
    etas = [po.eta for po in po_group if po.eta]
    if etas and min(etas) < date.today():
        return "overdue"
    if any(po.is_closed for po in po_group):
        return "closed"
    return "pending"


def _status_label(status: str) -> str:
    return {
        "closed": "已关闭",
        "pending": "待到料",
        "overdue": "逾期未到",
        "partial_received": "部分到",
        "fully_received": "已到齐",
    }.get(status, status)


async def _get_po_material_items(db: AsyncSession, order_no: str) -> list[KitAnalysisMaterialItem]:
    sync_filters = await get_purchase_order_sync_filters(db)
    result = await db.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.order_no == order_no, *sync_filters)
        .order_by(PurchaseOrder.material_code, PurchaseOrder.eta)
    )
    pos = result.scalars().all()

    po_groups: dict[str, list[PurchaseOrder]] = {}
    for po in pos:
        if po.material_code:
            po_groups.setdefault(po.material_code, []).append(po)

    items: list[KitAnalysisMaterialItem] = []
    for material_code, po_group in po_groups.items():
        etas = [po.eta for po in po_group if po.eta]
        arrivals = [po.actual_arrival_date for po in po_group if po.actual_arrival_date]
        inspections = [po.inspection_date for po in po_group if po.inspection_date]
        po_qty = _sum_decimal([po.po_qty for po in po_group])
        received_qty = _sum_decimal([po.received_qty for po in po_group])
        stagnant_qty = (
            received_qty - po_qty
            if received_qty is not None and po_qty is not None and received_qty > po_qty
            else None
        )
        status = _po_status(po_group)

        items.append(KitAnalysisMaterialItem(
            material_code=material_code,
            material_name=_pick_first([po.material_name for po in po_group]),
            material_property=_pick_first([po.material_property for po in po_group]),
            material_property_label=None,
            material_type=_pick_first([po.material_type_name for po in po_group]),
            supplier_name=_pick_first([po.supplier_name for po in po_group]),
            order_qty=_to_float(po_qty),
            shortage_qty=_to_float(po_qty - received_qty) if po_qty is not None and received_qty is not None and po_qty > received_qty else None,
            req_date=None,
            po_no=", ".join(dict.fromkeys([po.po_no for po in po_group if po.po_no])) or None,
            po_count=len(po_group),
            received_qty=_to_float(received_qty),
            eta=min(etas) if etas else None,
            first_eta=min(etas) if etas else None,
            latest_eta=max(etas) if etas else None,
            actual_arrival_date=max(arrivals) if arrivals else None,
            inspection_date=max(inspections) if inspections else None,
            status=status,
            status_label=_status_label(status),
            is_stagnant=stagnant_qty is not None,
            stagnant_qty=_to_float(stagnant_qty),
            is_closed=1 if any(po.is_closed for po in po_group) else 0,
        ))

    return items


async def _get_order_material_items(db: AsyncSession, order_no: str) -> list[KitAnalysisMaterialItem]:
    product_groups = await get_order_product_materials(db, order_no)
    items = [
        KitAnalysisMaterialItem(
            material_code=material.material_code,
            material_name=material.material_name,
            material_property=material.material_property,
            material_property_label=material.material_property_label,
            material_type=material.material_type,
            supplier_name=material.supplier_name,
            order_qty=material.req_qty,
            shortage_qty=material.shortage_qty,
            req_date=material.req_date,
            po_no=material.po_no,
            po_count=material.po_count,
            received_qty=material.received_qty,
            eta=material.eta,
            first_eta=material.first_eta,
            latest_eta=material.latest_eta,
            actual_arrival_date=material.actual_arrival_date,
            inspection_date=material.inspection_date,
            status=material.status,
            status_label=material.status_label,
            is_stagnant=material.is_stagnant,
            stagnant_qty=material.stagnant_qty,
            is_closed=material.is_closed,
        )
        for group in product_groups
        for material in group.materials
    ]

    po_items = await _get_po_material_items(db, order_no)
    known_material_codes = {item.material_code for item in items}
    items.extend(item for item in po_items if item.material_code not in known_material_codes)
    return items


async def get_kit_analysis(
    db: AsyncSession,
    order_no: Optional[str] = None,
    risk_level: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    only_pending_shipment: bool = False,
    promised_date_start: Optional[str] = None,
    promised_date_end: Optional[str] = None,
) -> dict:
    """Summarize material kit status by order, using one batched PO scan."""
    sync_filters = await get_purchase_order_sync_filters(db)
    po_query = select(
        PurchaseOrder.order_no,
        PurchaseOrder.material_code,
        PurchaseOrder.po_qty,
        PurchaseOrder.received_qty,
        PurchaseOrder.eta,
        PurchaseOrder.actual_arrival_date,
        PurchaseOrder.inspection_date,
    ).where(PurchaseOrder.order_no.is_not(None), *sync_filters)
    if order_no:
        po_query = po_query.where(PurchaseOrder.order_no.ilike(f"%{order_no}%"))

    po_result = await db.execute(po_query)
    material_groups: dict[tuple[str, str], dict] = {}
    for row in po_result:
        if not row.order_no or not row.material_code:
            continue
        key = (row.order_no, row.material_code)
        group = material_groups.setdefault(
            key,
            {
                "po_qty": Decimal("0"),
                "has_po_qty": False,
                "received_qty": Decimal("0"),
                "has_received_qty": False,
                "eta": None,
                "actual_arrival_date": None,
                "inspection_date": None,
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

    order_nos = sorted({current_order_no for current_order_no, _ in material_groups})

    promised_dates: dict[str, date | None] = {}
    pending_shipment_orders: set[str] = set()
    sale_order_nos: set[str] = set()
    closed_orders: set[str] = set()
    if order_nos:
        sale_order_result = await db.execute(
            select(SaleOrder.order_no, SaleOrder.promised_date, SaleOrder.delivery_completed_date, SaleOrder.is_closed)
            .where(SaleOrder.order_no.in_(order_nos))
            .distinct()
        )
        for row in sale_order_result:
            sale_order_nos.add(row.order_no)
            promised_dates.setdefault(row.order_no, row.promised_date)
            if row.delivery_completed_date is None:
                pending_shipment_orders.add(row.order_no)
            if row.is_closed == 1:
                closed_orders.add(row.order_no)

    if closed_orders:
        order_nos = [
            current_order_no
            for current_order_no in order_nos
            if current_order_no not in closed_orders
        ]

    if only_pending_shipment:
        order_nos = [
            current_order_no
            for current_order_no in order_nos
            if current_order_no not in sale_order_nos or current_order_no in pending_shipment_orders
        ]

    if promised_date_start or promised_date_end:
        start = date.fromisoformat(promised_date_start) if promised_date_start else None
        end = date.fromisoformat(promised_date_end) if promised_date_end else None
        filtered_order_nos = []
        for current_order_no in order_nos:
            promised_date = promised_dates.get(current_order_no)
            if promised_date is None:
                continue
            if start and promised_date < start:
                continue
            if end and promised_date > end:
                continue
            filtered_order_nos.append(current_order_no)
        order_nos = filtered_order_nos

    items: List[KitAnalysisItem] = []
    per_order: dict[str, list[dict]] = {}
    for (current_order_no, _), material_group in material_groups.items():
        per_order.setdefault(current_order_no, []).append(material_group)

    for current_order_no in order_nos:
        order_materials = per_order.get(current_order_no, [])
        total = len(order_materials)
        received_count = 0
        partial_count = 0
        overdue_count = 0
        stagnant_count = 0

        for material_group in order_materials:
            has_received = (
                material_group["has_received_qty"]
                and material_group["received_qty"] > 0
            )
            fully_received = (
                has_received
                and material_group["has_po_qty"]
                and material_group["received_qty"] >= material_group["po_qty"]
            )
            # 已到齐：收料数量 >= 需求数量
            if fully_received:
                received_count += 1
            # 部分到：0 < 收料数量 < 需求数量
            elif has_received:
                partial_count += 1
            # 逾期未到：无收料且交期早于今天
            elif material_group["eta"] and material_group["eta"] < date.today():
                overdue_count += 1
            # 呆滞：收料数量 > 下单数量
            if (
                material_group["has_po_qty"]
                and material_group["has_received_qty"]
                and material_group["received_qty"] > material_group["po_qty"]
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
            not_ordered_materials=0,
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
    order_qty_min: Optional[float] = None,
    order_qty_max: Optional[float] = None,
    received_qty_min: Optional[float] = None,
    received_qty_max: Optional[float] = None,
    eta_start: Optional[str] = None,
    eta_end: Optional[str] = None,
    actual_arrival_date_start: Optional[str] = None,
    actual_arrival_date_end: Optional[str] = None,
    inspection_date_start: Optional[str] = None,
    inspection_date_end: Optional[str] = None,
    is_stagnant: Optional[bool] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> List[KitAnalysisMaterialItem]:
    """Return complete order material details, including PO-only rows."""
    items = await _get_order_material_items(db, order_no)

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
    if order_qty_min is not None:
        items = [item for item in items if item.order_qty is not None and item.order_qty >= order_qty_min]
    if order_qty_max is not None:
        items = [item for item in items if item.order_qty is not None and item.order_qty <= order_qty_max]
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
