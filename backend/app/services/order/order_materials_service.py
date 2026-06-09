from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.material import Material
from app.models.material.binding import OrderMaterialPoBinding
from app.models.material.material_demand import MaterialDemand
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.schemas.order.schemas import OrderProductMaterialsOut, ProductMaterialItemOut


MATERIAL_PROPERTY_LABELS = {
    1: "外购",
    2: "自制",
    3: "委外加工",
    5: "虚拟件",
    6: "特征类",
    7: "配置类",
    8: "规划类",
    9: "组装件",
}

STATUS_LABELS = {
    "not_ordered": "未下单",
    "self_made_unlinked": "自制未排产/未关联",
    "pending": "待到料",
    "overdue": "逾期未到",
    "arrived": "已到料",
    "inspected": "已检验",
}


@dataclass
class MaterialPoSummary:
    po_no: Optional[str] = None
    supplier_name: Optional[str] = None
    material_property: Optional[int] = None
    material_type_name: Optional[str] = None
    material_name: Optional[str] = None
    po_qty: Optional[Decimal] = None
    received_qty: Optional[Decimal] = None
    first_eta: Optional[date] = None
    latest_eta: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    inspection_date: Optional[date] = None
    po_count: int = 0

    @property
    def eta(self) -> Optional[date]:
        return self.first_eta


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _sum_qty(values) -> Optional[Decimal]:
    total = Decimal("0")
    seen = False
    for value in values:
        if value is not None:
            total += value
            seen = True
    return total if seen else None


def _pick_first(values):
    return next((value for value in values if value not in (None, "")), None)


def _summarize_pos(pos: list[PurchaseOrder]) -> Optional[MaterialPoSummary]:
    if not pos:
        return None
    etas = [po.eta for po in pos if po.eta]
    arrivals = [po.actual_arrival_date for po in pos if po.actual_arrival_date]
    inspections = [po.inspection_date for po in pos if po.inspection_date]
    return MaterialPoSummary(
        po_no=", ".join(dict.fromkeys([po.po_no for po in pos if po.po_no])) or None,
        supplier_name=_pick_first([po.supplier_name for po in pos]),
        material_property=_pick_first([po.material_property for po in pos]),
        material_type_name=_pick_first([po.material_type_name for po in pos]),
        material_name=_pick_first([po.material_name for po in pos]),
        po_qty=_sum_qty([po.po_qty for po in pos]),
        received_qty=_sum_qty([po.received_qty for po in pos]),
        first_eta=min(etas) if etas else None,
        latest_eta=max(etas) if etas else None,
        actual_arrival_date=max(arrivals) if arrivals else None,
        inspection_date=max(inspections) if inspections else None,
        po_count=len(pos),
    )


def _infer_material_property(demand: MaterialDemand, po_summary: Optional[MaterialPoSummary], master: Optional[Material]) -> Optional[int]:
    if getattr(demand, "material_property", None):
        return demand.material_property
    if po_summary and po_summary.material_property:
        return po_summary.material_property
    if master:
        if master.is_purchase:
            return 1
        if master.is_produce:
            return 2
    return None


def _material_property_label(material_property: Optional[int]) -> Optional[str]:
    if material_property is None:
        return None
    return MATERIAL_PROPERTY_LABELS.get(material_property, str(material_property))


def _status(material_property: Optional[int], po_summary: Optional[MaterialPoSummary]) -> str:
    if not po_summary or po_summary.po_count == 0:
        return "self_made_unlinked" if material_property == 2 else "not_ordered"
    if po_summary.inspection_date:
        return "inspected"
    if po_summary.actual_arrival_date or (po_summary.received_qty is not None and po_summary.received_qty > 0):
        return "arrived"
    if po_summary.eta and po_summary.eta < date.today():
        return "overdue"
    return "pending"


def _kit_met(status: str, material_property: Optional[int]) -> bool:
    if material_property == 2 and status == "self_made_unlinked":
        return True
    return status in {"arrived", "inspected"}


async def get_order_product_materials(
    db: AsyncSession,
    order_no: str,
    line_no: Optional[str] = None,
) -> list[OrderProductMaterialsOut]:
    line_query = select(SaleOrderLine).where(SaleOrderLine.order_no == order_no)
    if line_no:
        line_query = line_query.where(SaleOrderLine.line_no == line_no)
    line_result = await db.execute(line_query.order_by(SaleOrderLine.id))
    lines = line_result.scalars().all()

    if not lines:
        order_query = select(SaleOrder).where(SaleOrder.order_no == order_no)
        if line_no:
            order_query = order_query.where(SaleOrder.line_no == line_no)
        order = (await db.execute(order_query)).scalar_one_or_none()
        if order:
            lines = [
                SimpleNamespace(
                    order_no=order.order_no,
                    line_no=order.line_no,
                    product_code=order.product_code,
                    product_name=order.product_name,
                    product_model=None,
                    order_qty=order.order_qty,
                    promised_date=order.promised_date,
                )
            ]

    line_nos = [line.line_no for line in lines if line.line_no]
    demand_query = select(MaterialDemand).where(MaterialDemand.order_no == order_no)
    if line_no:
        demand_query = demand_query.where(MaterialDemand.line_no == line_no)
    elif line_nos:
        demand_query = demand_query.where(MaterialDemand.line_no.in_(line_nos))
    demand_result = await db.execute(demand_query.order_by(MaterialDemand.line_no, MaterialDemand.material_code))
    demands = demand_result.scalars().all()

    material_codes = sorted({d.material_code for d in demands if d.material_code})
    master_map: dict[str, Material] = {}
    if material_codes:
        master_result = await db.execute(select(Material).where(Material.material_code.in_(material_codes)))
        master_map = {m.material_code: m for m in master_result.scalars().all()}

    binding_pos: dict[tuple[str, str], list[PurchaseOrder]] = {}
    if material_codes:
        binding_query = (
            select(OrderMaterialPoBinding, PurchaseOrder)
            .join(PurchaseOrder, PurchaseOrder.po_no == OrderMaterialPoBinding.po_no, isouter=True)
            .where(OrderMaterialPoBinding.order_no == order_no)
        )
        if line_no:
            binding_query = binding_query.where(OrderMaterialPoBinding.line_no == line_no)
        elif line_nos:
            binding_query = binding_query.where(OrderMaterialPoBinding.line_no.in_(line_nos))
        binding_query = binding_query.where(OrderMaterialPoBinding.material_code.in_(material_codes))
        binding_result = await db.execute(binding_query)
        for binding, po in binding_result.all():
            if po:
                binding_pos.setdefault((binding.line_no, binding.material_code), []).append(po)

    fallback_pos: dict[str, list[PurchaseOrder]] = {}
    if material_codes:
        po_result = await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.order_no == order_no,
                PurchaseOrder.material_code.in_(material_codes),
            )
        )
        for po in po_result.scalars().all():
            fallback_pos.setdefault(po.material_code, []).append(po)

    demands_by_line: dict[str, list[MaterialDemand]] = {}
    for demand in demands:
        demands_by_line.setdefault(demand.line_no or "", []).append(demand)

    result: list[OrderProductMaterialsOut] = []
    seen_lines = set()
    for line in lines:
        line_key = line.line_no or ""
        seen_lines.add(line_key)
        line_demands = demands_by_line.get(line_key, [])
        result.append(_build_line_materials(line, line_demands, binding_pos, fallback_pos, master_map))

    for line_key, line_demands in demands_by_line.items():
        if line_key in seen_lines:
            continue
        synthetic_line = SimpleNamespace(
            order_no=order_no,
            line_no=line_key,
            product_code=None,
            product_name=None,
            product_model=None,
            order_qty=None,
            promised_date=None,
        )
        result.append(_build_line_materials(synthetic_line, line_demands, binding_pos, fallback_pos, master_map))

    return result


def _build_line_materials(
    line: SaleOrderLine,
    demands: list[MaterialDemand],
    binding_pos: dict[tuple[str, str], list[PurchaseOrder]],
    fallback_pos: dict[str, list[PurchaseOrder]],
    master_map: dict[str, Material],
) -> OrderProductMaterialsOut:
    items: list[ProductMaterialItemOut] = []
    for demand in demands:
        pos = binding_pos.get((demand.line_no, demand.material_code)) or fallback_pos.get(demand.material_code, [])
        po_summary = _summarize_pos(pos)
        master = master_map.get(demand.material_code)
        material_property = _infer_material_property(demand, po_summary, master)
        status = _status(material_property, po_summary)
        material_type = (
            getattr(demand, "material_type_name", None)
            or (po_summary.material_type_name if po_summary else None)
            or (master.material_type if master else None)
        )
        received_qty = po_summary.received_qty if po_summary else None
        po_qty = po_summary.po_qty if po_summary else None
        stagnant_qty = received_qty - po_qty if received_qty is not None and po_qty is not None and received_qty > po_qty else None

        items.append(ProductMaterialItemOut(
            material_code=demand.material_code,
            material_name=demand.material_name or (po_summary.material_name if po_summary else None) or (master.material_name if master else None),
            material_property=material_property,
            material_property_label=_material_property_label(material_property),
            material_type=material_type,
            spec_model=getattr(demand, "spec_model", None) or (master.spec_model if master else None),
            unit=getattr(demand, "unit", None) or (master.unit_of_measure if master else None),
            req_qty=_to_float(demand.req_qty),
            req_date=demand.req_date,
            allocated_qty=float(demand.allocated_qty or 0),
            shortage_qty=float(demand.shortage_qty or 0),
            shortage_flag=bool(demand.shortage_flag),
            status=status,
            status_label=STATUS_LABELS.get(status, status),
            po_no=po_summary.po_no if po_summary else None,
            supplier_name=po_summary.supplier_name if po_summary else None,
            po_qty=_to_float(po_qty),
            received_qty=_to_float(received_qty),
            eta=po_summary.eta if po_summary else None,
            first_eta=po_summary.first_eta if po_summary else None,
            latest_eta=po_summary.latest_eta if po_summary else None,
            actual_arrival_date=po_summary.actual_arrival_date if po_summary else None,
            inspection_date=po_summary.inspection_date if po_summary else None,
            po_count=po_summary.po_count if po_summary else 0,
            is_stagnant=stagnant_qty is not None,
            stagnant_qty=_to_float(stagnant_qty),
        ))

    total = len(items)
    arrived = sum(1 for item in items if item.status in {"arrived", "inspected"})
    inspected = sum(1 for item in items if item.status == "inspected")
    not_ordered = sum(1 for item in items if item.status == "not_ordered")
    overdue = sum(1 for item in items if item.status == "overdue")
    shortage = sum(1 for item in items if item.shortage_flag or item.shortage_qty > 0)
    met = sum(1 for item in items if _kit_met(item.status, item.material_property))

    return OrderProductMaterialsOut(
        line_no=line.line_no,
        product_code=line.product_code,
        product_name=line.product_name,
        product_model=getattr(line, "product_model", None),
        order_qty=_to_float(line.order_qty),
        promised_date=line.promised_date,
        total_materials=total,
        not_ordered_count=not_ordered,
        shortage_count=shortage,
        overdue_count=overdue,
        arrived_count=arrived,
        inspected_count=inspected,
        kit_rate=round(met / total, 4) if total else 0,
        materials=items,
    )
