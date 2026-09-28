"""MRP 快照采集：需求 / 供给 / BOM 上下文（只读）。"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.bom import Bom
from app.models.basicdata.bom_detail import BomDetail
from app.models.basicdata.inventory import Inventory
from app.models.basicdata.material import Material
from app.models.material.purchase_order import PurchaseOrder
from app.models.material.purchase_requisition import PurchaseRequisition, PurchaseRequisitionLine
from app.models.material.subcontract_order import SubcontractOrder
from app.models.material.subcontract_order_detail import SubcontractOrderDetail
from app.models.material.transfer_order import TransferOrder
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.production.production_task_order import ProductionTaskOrder

_ZERO = Decimal("0")


@dataclass(frozen=True)
class DemandRecord:
    material_id: int
    need_date: Optional[date]
    qty: Decimal
    order_no: str
    line_no: str


@dataclass(frozen=True)
class SupplyRecord:
    material_id: int
    supply_date: Optional[date]
    qty: Decimal
    source_type: str  # po / task / subcontract / transfer / requisition
    source_doc_no: str
    source_line_no: str
    source_id: int


@dataclass(frozen=True)
class BomComponentRef:
    material_id: int
    standard_qty: Decimal
    scrap_rate: Decimal
    lead_offset_days: int
    valid_date: Optional[date]
    invalid_date: Optional[date]


@dataclass
class Snapshot:
    demands: list[DemandRecord] = field(default_factory=list)
    supplies: list[SupplyRecord] = field(default_factory=list)
    opening_by_material: dict[int, Decimal] = field(default_factory=dict)
    code_by_material: dict[int, str] = field(default_factory=dict)
    name_by_material: dict[int, str] = field(default_factory=dict)
    property_by_material: dict[int, Optional[int]] = field(default_factory=dict)
    bom_parent_by_id: dict[str, int] = field(default_factory=dict)
    details_by_bom: dict[str, list[BomComponentRef]] = field(default_factory=dict)
    bom_by_material: dict[int, str] = field(default_factory=dict)
    phantom_ids: set[int] = field(default_factory=set)
    data_issues: dict[str, list] = field(default_factory=dict)


def _add_issue(snapshot: Snapshot, key: str, payload: dict) -> None:
    snapshot.data_issues.setdefault(key, []).append(payload)


async def _load_materials(db: AsyncSession, snapshot: Snapshot) -> dict[str, int]:
    rows = (
        await db.execute(
            select(
                Material.erp_material_id, Material.material_code, Material.material_name,
                Material.material_property,
            ).where(Material.erp_material_id.isnot(None))
        )
    ).all()
    code_to_id: dict[str, int] = {}
    for erp_id, code, name, prop in rows:
        mid = int(erp_id)
        snapshot.property_by_material[mid] = prop
        if code:
            snapshot.code_by_material[mid] = code
            code_to_id[code] = mid
        if name:
            snapshot.name_by_material[mid] = name
        if prop == 5:
            snapshot.phantom_ids.add(mid)
    return code_to_id


async def _load_bom_context(db: AsyncSession, snapshot: Snapshot) -> None:
    bom_rows = (
        await db.execute(
            select(Bom.bom_id, Bom.material_id, Bom.id)
            .where(Bom.is_audited == 1, Bom.disabled_status == 0, Bom.void_flag == 0)
            .order_by(Bom.id)
        )
    ).all()
    for bom_id, material_id, _pk in bom_rows:
        if bom_id and material_id is not None:
            snapshot.bom_parent_by_id[str(bom_id)] = int(material_id)
            snapshot.bom_by_material[int(material_id)] = str(bom_id)  # 后写覆盖=取 id 最大

    detail_rows = (
        await db.execute(
            select(
                BomDetail.bom_id, BomDetail.material_id, BomDetail.standard_qty,
                BomDetail.scrap_rate, BomDetail.lead_offset_days,
                BomDetail.valid_date, BomDetail.invalid_date,
            )
        )
    ).all()
    for bom_id, material_id, standard_qty, scrap_rate, lead_offset, valid_date, invalid_date in detail_rows:
        if not bom_id or material_id is None or standard_qty is None:
            continue
        snapshot.details_by_bom.setdefault(str(bom_id), []).append(
            BomComponentRef(
                material_id=int(material_id),
                standard_qty=Decimal(str(standard_qty)),
                scrap_rate=Decimal(str(scrap_rate)) if scrap_rate is not None else _ZERO,
                lead_offset_days=int(lead_offset or 0),
                valid_date=valid_date,
                invalid_date=invalid_date,
            )
        )


async def _load_demands(db: AsyncSession, snapshot: Snapshot, scope: dict) -> None:
    rows = (
        await db.execute(
            select(
                SaleOrderLine.order_no, SaleOrderLine.line_no, SaleOrderLine.order_qty,
                SaleOrderLine.promised_date, SaleOrderLine.bom_id,
                SaleOrder.completed_qty, SaleOrder.shipping_plan, SaleOrder.promised_date,
            )
            .join(SaleOrder, SaleOrderLine.sale_order_id == SaleOrder.id)
            .where(
                SaleOrder.is_closed == 0,
                SaleOrder.is_deleted == 0,
                SaleOrderLine.status != "closed",
            )
        )
    ).all()
    scope_order_no = scope.get("sale_order_no")
    scope_codes = {str(c) for c in (scope.get("material_codes") or [])}
    for order_no, line_no, order_qty, line_promised, bom_id, completed_qty, ship_plan, header_promised in rows:
        if scope_order_no and order_no != scope_order_no:
            continue
        qty = (Decimal(str(order_qty)) if order_qty is not None else _ZERO) - (
            Decimal(str(completed_qty)) if completed_qty is not None else _ZERO
        )
        if qty <= 0:
            continue
        parent_material_id = snapshot.bom_parent_by_id.get(str(bom_id)) if bom_id is not None else None
        if scope_codes and snapshot.code_by_material.get(parent_material_id) not in scope_codes:
            continue
        if bom_id is None or parent_material_id is None:
            _add_issue(snapshot, "demand_without_bom", {"order_no": order_no, "line_no": line_no})
            continue
        need_date = line_promised or ship_plan or header_promised
        if need_date is None:
            _add_issue(snapshot, "demand_no_date", {"order_no": order_no, "line_no": line_no})
        snapshot.demands.append(
            DemandRecord(
                material_id=parent_material_id,
                need_date=need_date,
                qty=qty,
                order_no=order_no or "",
                line_no=line_no or "",
            )
        )


async def _load_supplies(db: AsyncSession, snapshot: Snapshot, code_to_id: dict[str, int]) -> None:
    inv_rows = (
        await db.execute(
            select(Inventory.material_id, func.sum(Inventory.qty_on_hand - Inventory.locked_qty))
            .where(Inventory.material_id.isnot(None))
            .group_by(Inventory.material_id)
        )
    ).all()
    for material_id, qty in inv_rows:
        snapshot.opening_by_material[int(material_id)] = Decimal(str(qty or 0))

    po_rows = (
        await db.execute(
            select(
                PurchaseOrder.id, PurchaseOrder.po_no, PurchaseOrder.detail_id,
                PurchaseOrder.material_code, PurchaseOrder.po_qty,
                PurchaseOrder.received_qty, PurchaseOrder.eta, PurchaseOrder.po_date,
            ).where(PurchaseOrder.is_closed == 0, PurchaseOrder.material_code.isnot(None))
        )
    ).all()
    for pk, po_no, detail_id, material_code, po_qty, received_qty, eta, po_date in po_rows:
        mid = code_to_id.get(material_code)
        if mid is None:
            continue
        qty = (Decimal(str(po_qty)) if po_qty is not None else _ZERO) - (
            Decimal(str(received_qty)) if received_qty is not None else _ZERO
        )
        if qty <= 0:
            continue
        snapshot.supplies.append(
            SupplyRecord(mid, eta or po_date, qty, "po", po_no or "", str(detail_id or ""), int(pk))
        )

    task_rows = (
        await db.execute(
            select(
                ProductionTaskOrder.id, ProductionTaskOrder.task_no, ProductionTaskOrder.material_code,
                ProductionTaskOrder.task_qty, ProductionTaskOrder.actual_qty,
                ProductionTaskOrder.planned_end_date, ProductionTaskOrder.planned_start_date,
            ).where(
                (ProductionTaskOrder.is_closed == 0) | (ProductionTaskOrder.is_closed.is_(None)),
                ProductionTaskOrder.material_code.isnot(None),
            )
        )
    ).all()
    for pk, task_no, material_code, task_qty, actual_qty, end_date, start_date in task_rows:
        mid = code_to_id.get(material_code)
        if mid is None:
            continue
        qty = (Decimal(str(task_qty)) if task_qty is not None else _ZERO) - (
            Decimal(str(actual_qty)) if actual_qty is not None else _ZERO
        )
        if qty <= 0:
            continue
        snapshot.supplies.append(
            SupplyRecord(mid, end_date or start_date, qty, "task", task_no or "", "", int(pk))
        )

    sub_rows = (
        await db.execute(
            select(
                SubcontractOrderDetail.id, SubcontractOrder.bill_no, SubcontractOrderDetail.detail_id,
                SubcontractOrderDetail.material_id, SubcontractOrderDetail.qty,
                SubcontractOrderDetail.received_qty, SubcontractOrderDetail.returned_qty,
                SubcontractOrder.bill_date,
            )
            .join(SubcontractOrder, SubcontractOrderDetail.erp_order_id == SubcontractOrder.erp_order_id)
            .where(
                (SubcontractOrder.closed_flag == 0) | (SubcontractOrder.closed_flag.is_(None)),
                (SubcontractOrder.voided_flag == 0) | (SubcontractOrder.voided_flag.is_(None)),
                SubcontractOrderDetail.material_id.isnot(None),
            )
        )
    ).all()
    for pk, bill_no, detail_id, material_id, qty, received_qty, returned_qty, bill_date in sub_rows:
        outstanding = (
            (Decimal(str(qty)) if qty is not None else _ZERO)
            - (Decimal(str(received_qty)) if received_qty is not None else _ZERO)
            - (Decimal(str(returned_qty)) if returned_qty is not None else _ZERO)
        )
        if outstanding <= 0:
            continue
        snapshot.supplies.append(
            SupplyRecord(int(material_id), bill_date, outstanding, "subcontract", bill_no or "", str(detail_id or ""), int(pk))
        )
    _add_issue(snapshot, "subcontract_date_approx", {"note": "委外供给日期暂用单据日期 bill_date（K3 未同步预计到货日）"})

    tr_rows = (
        await db.execute(
            select(
                TransferOrder.id, TransferOrder.transfer_no, TransferOrder.entry_id,
                TransferOrder.material_code, TransferOrder.qty,
                TransferOrder.expected_arrival_date, TransferOrder.transfer_date,
            ).where(TransferOrder.is_deleted == 0, TransferOrder.status == "in_transit")
        )
    ).all()
    for pk, transfer_no, entry_id, material_code, qty, expected_arrival, transfer_date in tr_rows:
        mid = code_to_id.get(material_code) if material_code else None
        if mid is None or qty is None or Decimal(str(qty)) <= 0:
            continue
        snapshot.supplies.append(
            SupplyRecord(mid, expected_arrival or transfer_date, Decimal(str(qty)), "transfer", transfer_no or "", str(entry_id or ""), int(pk))
        )

    req_rows = (
        await db.execute(
            select(
                PurchaseRequisitionLine.id, PurchaseRequisition.req_no,
                PurchaseRequisitionLine.line_no, PurchaseRequisitionLine.material_code,
                PurchaseRequisitionLine.req_qty, PurchaseRequisitionLine.converted_qty,
                PurchaseRequisitionLine.need_date,
            )
            .join(PurchaseRequisition, PurchaseRequisitionLine.req_id == PurchaseRequisition.id)
            .where(
                PurchaseRequisition.status == "approved",
                PurchaseRequisitionLine.status.in_(["open", "partially_converted"]),
                PurchaseRequisitionLine.material_code.isnot(None),
            )
        )
    ).all()
    for pk, req_no, line_no, material_code, req_qty, converted_qty, need_date in req_rows:
        mid = code_to_id.get(material_code)
        if mid is None:
            continue
        outstanding = (Decimal(str(req_qty)) if req_qty is not None else _ZERO) - (
            Decimal(str(converted_qty)) if converted_qty is not None else _ZERO
        )
        if outstanding <= 0:
            continue
        snapshot.supplies.append(
            SupplyRecord(mid, need_date, outstanding, "requisition", req_no or "", str(line_no or ""), int(pk))
        )


async def collect(db: AsyncSession, scope: Optional[dict] = None) -> Snapshot:
    snapshot = Snapshot()
    code_to_id = await _load_materials(db, snapshot)
    await _load_bom_context(db, snapshot)
    await _load_demands(db, snapshot, scope or {})
    await _load_supplies(db, snapshot, code_to_id)
    return snapshot
