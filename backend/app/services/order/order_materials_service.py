from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.bom import Bom
from app.models.basicdata.bom_detail import BomDetail
from app.models.basicdata.material import Material
from app.models.material.binding import OrderMaterialPoBinding
from app.models.material.material_demand import MaterialDemand
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.schemas.order.schemas import BomDetailItemOut, OrderProductMaterialsOut


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
    "partial_received": "部分到",
    "fully_received": "已到齐",
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
    is_closed: int = 0

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
        is_closed=1 if any(po.is_closed for po in pos) else 0,
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
    received_qty = po_summary.received_qty
    po_qty = po_summary.po_qty
    # 状态纯按收料数量推导（已到料状态已移除）
    if received_qty is not None and received_qty > 0:
        if po_qty is not None and received_qty >= po_qty:
            return "fully_received"
        return "partial_received"
    if po_summary.eta and po_summary.eta < date.today():
        return "overdue"
    return "pending"


def _kit_met(status: str, material_property: Optional[int]) -> bool:
    if material_property == 2 and status == "self_made_unlinked":
        return True
    # 仅「已到齐」视为齐套；部分到（缺量）不计入
    return status == "fully_received"


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
                    bom_id=None,
                )
            ]

    # 直接通过 sale_order_line.bom_id 关联 scm_bom_detail.bom_id（bom_id 转字符串匹配）
    line_bom_ids = sorted({str(line.bom_id) for line in lines if getattr(line, "bom_id", None)})
    bom_details_by_id: dict[str, list[BomDetail]] = {}
    if line_bom_ids:
        detail_result = await db.execute(
            select(BomDetail).where(BomDetail.bom_id.in_(line_bom_ids)).order_by(BomDetail.bom_id, BomDetail.line_no)
        )
        for detail in detail_result.scalars().all():
            bom_details_by_id.setdefault(detail.bom_id, []).append(detail)

    # 物料主数据：按 BOM 明细的 material_id 取
    bom_detail_material_ids = sorted({
        d.material_id for details in bom_details_by_id.values() for d in details if d.material_id
    })
    master_by_mid: dict[str, Material] = {}
    if bom_detail_material_ids:
        mid_result = await db.execute(select(Material).where(Material.material_id.in_(bom_detail_material_ids)))
        for m in mid_result.scalars().all():
            master_by_mid[m.material_id] = m

    result: list[OrderProductMaterialsOut] = []
    for line in lines:
        line_bom_id = str(line.bom_id) if getattr(line, "bom_id", None) else None
        line_bom_details = bom_details_by_id.get(line_bom_id, []) if line_bom_id else []
        result.append(_build_line_materials(line, line_bom_details, master_by_mid))

    return result


def _build_line_materials(
    line: SaleOrderLine,
    bom_details: list[BomDetail],
    master_by_mid: dict[str, Material],
) -> OrderProductMaterialsOut:
    order_qty = line.order_qty

    items: list[BomDetailItemOut] = []
    for detail in bom_details:
        master = master_by_mid.get(detail.material_id) if detail.material_id else None
        # 需求量 = BOM 明细标准用量 × 订单数量
        if detail.standard_qty is not None and order_qty is not None:
            req_qty = _to_float(detail.standard_qty * order_qty)
        else:
            req_qty = _to_float(detail.standard_qty)

        items.append(BomDetailItemOut(
            material_id=detail.material_id,
            material_code=master.material_code if master else None,
            material_name=master.material_name if master else None,
            spec_model=master.spec_model if master else None,
            unit=master.unit_of_measure if master else None,
            material_type=detail.material_type or (master.material_type if master else None),
            line_no=detail.line_no,
            standard_qty=_to_float(detail.standard_qty),
            aux_qty=_to_float(detail.aux_qty),
            config_type=detail.config_type,
            lead_offset_days=detail.lead_offset_days,
            back_flush=detail.back_flush,
            scrap_rate=_to_float(detail.scrap_rate),
            oper_sn=detail.oper_sn,
            process_id=detail.process_id,
            warehouse_id=detail.warehouse_id,
            valid_date=detail.valid_date,
            invalid_date=detail.invalid_date,
            kit_flag=detail.kit_flag,
            req_qty=req_qty,
        ))

    total = len(items)

    return OrderProductMaterialsOut(
        line_no=line.line_no,
        product_code=line.product_code,
        product_name=line.product_name,
        product_model=getattr(line, "product_model", None),
        order_qty=_to_float(line.order_qty),
        promised_date=line.promised_date,
        total_materials=total,
        materials=items,
    )
