"""订单覆盖视图：给定销售订单号，逐行看需求被哪些供给覆盖。只读。

需求行过滤口径同 snapshot._load_demands（未关单/未删单/行未关闭），
供给装载逐段镜像 snapshot._load_supplies（库存/未结 PO/未结任务/委外/调拨/已批准申请单），
仅按本单涉及物料收窄 SQL，保证与 MRP 运算同源。
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.bom import Bom
from app.models.basicdata.inventory import Inventory
from app.models.material.purchase_order import PurchaseOrder
from app.models.material.purchase_requisition import PurchaseRequisition, PurchaseRequisitionLine
from app.models.material.subcontract_order import SubcontractOrder
from app.models.material.subcontract_order_detail import SubcontractOrderDetail
from app.models.material.transfer_order import TransferOrder
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.production.production_task_order import ProductionTaskOrder
from app.services.mrp.snapshot import Snapshot, _load_materials

_ZERO = Decimal("0")
_NOTE = "供给=库存+未结采购+未结任务+委外+调拨+已批准申请单；拖期单据按今天计入"


def _decimal(value) -> Decimal:
    return Decimal(str(value)) if value is not None else _ZERO


def _supply(source_type: str, doc_no: str, line_no, qty: Decimal, supply_date) -> dict:
    return {
        "source_type": source_type,
        "doc_no": doc_no,
        "line_no": line_no,
        "qty": float(qty),
        "date": supply_date,
    }


def _serialize_supplies(supplies: list[dict]) -> list[dict]:
    return [
        {
            "source_type": s["source_type"],
            "doc_no": s["doc_no"],
            "line_no": s["line_no"],
            "qty": s["qty"],
            "date": s["date"].isoformat() if s["date"] else None,
            "used": s["used"],
        }
        for s in supplies
    ]


def _allocate_fifo(supplies: list[dict], demand: Decimal) -> tuple[Decimal, list[dict]]:
    """按日期 FIFO 分配供给到需求；返回 (covered, 供给全量带本行 used 占用)。

    供给条目以内部字段 _remaining 记录剩余可分配量：同物料多行按行序调用时原地扣减，
    后行不会重复占用前行已耗用的供给；每行仍返回全量供给列表（未占用 used=0）。
    """
    remaining = demand
    allocated: list[dict] = []
    for supply in sorted(supplies, key=lambda s: s["date"] or date.min):
        available = supply.setdefault("_remaining", _decimal(supply["qty"]))
        if remaining <= 0:
            allocated.append({**supply, "used": 0.0})
            continue
        take = min(available, remaining)
        supply["_remaining"] = available - take
        remaining -= take
        allocated.append({**supply, "used": float(take)})
    return demand - remaining, allocated


async def _fetch_order_rows(db: AsyncSession, order_no: str):
    return (
        await db.execute(
            select(
                SaleOrderLine.line_no, SaleOrderLine.product_code, SaleOrderLine.product_name,
                SaleOrderLine.order_qty, SaleOrder.completed_qty,
                SaleOrderLine.promised_date, SaleOrder.shipping_plan, SaleOrder.promised_date,
                SaleOrderLine.bom_id,
            )
            .join(SaleOrder, SaleOrderLine.sale_order_id == SaleOrder.id)
            .where(
                SaleOrder.order_no == order_no,
                SaleOrder.is_closed == 0,
                SaleOrder.is_deleted == 0,
                SaleOrderLine.status != "closed",
            )
            .order_by(SaleOrderLine.line_no)
        )
    ).all()


async def _load_bom_parents(db: AsyncSession) -> dict[str, int]:
    # 过滤口径与 snapshot._load_bom_context 对齐；按 id 升序后写覆盖=取最新 BOM
    rows = (
        await db.execute(
            select(Bom.bom_id, Bom.material_id)
            .where(
                Bom.material_id.isnot(None),
                Bom.is_audited == 1,
                Bom.disabled_status == 0,
                Bom.void_flag == 0,
            )
            .order_by(Bom.id)
        )
    ).all()
    return {str(bom_id): int(material_id) for bom_id, material_id in rows}


def _build_lines(rows, bom_parent, code_by_material, name_by_material):
    lines: list[dict] = []
    total_qty = _ZERO
    for line_no, product_code, product_name, order_qty, completed_qty, line_promised, ship_plan, header_promised, bom_id in rows:
        qty = _decimal(order_qty) - _decimal(completed_qty)
        if qty <= 0:
            continue
        total_qty += qty
        material_id = bom_parent.get(str(bom_id)) if bom_id is not None else None
        need_date = line_promised or ship_plan or header_promised
        lines.append({
            "line_no": line_no,
            "product_code": product_code,
            "product_name": product_name or (name_by_material.get(material_id) if material_id is not None else None),
            "material_id": material_id,
            "material_code": code_by_material.get(material_id) if material_id is not None else None,
            "qty": float(qty),
            "need_date": need_date.isoformat() if need_date else None,
            "bom_id": str(bom_id) if bom_id is not None else None,
            "supplies": [],
            "covered_qty": 0.0,
            "shortage_qty": float(qty),
            "status": "short",
        })
    return lines, total_qty


async def _load_inventory_supplies(db: AsyncSession, supplies, material_ids: set[int]) -> None:
    rows = (
        await db.execute(
            select(Inventory.material_id, func.sum(Inventory.qty_on_hand - Inventory.locked_qty))
            .where(Inventory.material_id.in_(material_ids))
            .group_by(Inventory.material_id)
        )
    ).all()
    for material_id, qty in rows:
        if qty and _decimal(qty) > 0:
            supplies[int(material_id)].append(_supply("inventory", "库存", None, _decimal(qty), None))


async def _load_purchase_order_supplies(db: AsyncSession, supplies, mid_by_code: dict[str, int]) -> None:
    rows = (
        await db.execute(
            select(
                PurchaseOrder.po_no, PurchaseOrder.detail_id, PurchaseOrder.material_code,
                PurchaseOrder.po_qty, PurchaseOrder.received_qty, PurchaseOrder.eta, PurchaseOrder.po_date,
            ).where(PurchaseOrder.is_closed == 0, PurchaseOrder.material_code.in_(list(mid_by_code)))
        )
    ).all()
    for po_no, detail_id, material_code, po_qty, received_qty, eta, po_date in rows:
        mid = mid_by_code.get(material_code)
        if mid is None:
            continue
        qty = _decimal(po_qty) - _decimal(received_qty)
        if qty <= 0:
            continue
        supplies[mid].append(_supply("po", po_no or "", str(detail_id or ""), qty, eta or po_date))


async def _load_task_supplies(db: AsyncSession, supplies, mid_by_code: dict[str, int]) -> None:
    rows = (
        await db.execute(
            select(
                ProductionTaskOrder.task_no, ProductionTaskOrder.material_code,
                ProductionTaskOrder.task_qty, ProductionTaskOrder.actual_qty,
                ProductionTaskOrder.planned_end_date, ProductionTaskOrder.planned_start_date,
            ).where(
                (ProductionTaskOrder.is_closed == 0) | (ProductionTaskOrder.is_closed.is_(None)),
                ProductionTaskOrder.material_code.in_(list(mid_by_code)),
            )
        )
    ).all()
    for task_no, material_code, task_qty, actual_qty, end_date, start_date in rows:
        mid = mid_by_code.get(material_code)
        if mid is None:
            continue
        qty = _decimal(task_qty) - _decimal(actual_qty)
        if qty <= 0:
            continue
        supplies[mid].append(_supply("task", task_no or "", None, qty, end_date or start_date))


async def _load_subcontract_supplies(db: AsyncSession, supplies, material_ids: set[int]) -> None:
    rows = (
        await db.execute(
            select(
                SubcontractOrder.bill_no, SubcontractOrderDetail.detail_id,
                SubcontractOrderDetail.material_id, SubcontractOrderDetail.qty,
                SubcontractOrderDetail.received_qty, SubcontractOrderDetail.returned_qty,
                SubcontractOrder.bill_date,
            )
            .join(SubcontractOrder, SubcontractOrderDetail.erp_order_id == SubcontractOrder.erp_order_id)
            .where(
                (SubcontractOrder.closed_flag == 0) | (SubcontractOrder.closed_flag.is_(None)),
                (SubcontractOrder.voided_flag == 0) | (SubcontractOrder.voided_flag.is_(None)),
                SubcontractOrderDetail.material_id.in_(material_ids),
            )
        )
    ).all()
    for bill_no, detail_id, material_id, qty, received_qty, returned_qty, bill_date in rows:
        outstanding = _decimal(qty) - _decimal(received_qty) - _decimal(returned_qty)
        if outstanding <= 0:
            continue
        supplies[int(material_id)].append(
            _supply("subcontract", bill_no or "", str(detail_id or ""), outstanding, bill_date)
        )


async def _load_transfer_supplies(db: AsyncSession, supplies, mid_by_code: dict[str, int]) -> None:
    rows = (
        await db.execute(
            select(
                TransferOrder.transfer_no, TransferOrder.entry_id, TransferOrder.material_code,
                TransferOrder.qty, TransferOrder.expected_arrival_date, TransferOrder.transfer_date,
            ).where(
                TransferOrder.is_deleted == 0,
                TransferOrder.status == "in_transit",
                TransferOrder.material_code.in_(list(mid_by_code)),
            )
        )
    ).all()
    for transfer_no, entry_id, material_code, qty, expected_arrival, transfer_date in rows:
        mid = mid_by_code.get(material_code)
        if mid is None or qty is None or _decimal(qty) <= 0:
            continue
        supplies[mid].append(
            _supply("transfer", transfer_no or "", str(entry_id or ""), _decimal(qty), expected_arrival or transfer_date)
        )


async def _load_requisition_supplies(db: AsyncSession, supplies, mid_by_code: dict[str, int]) -> None:
    rows = (
        await db.execute(
            select(
                PurchaseRequisition.req_no, PurchaseRequisitionLine.line_no,
                PurchaseRequisitionLine.material_code, PurchaseRequisitionLine.req_qty,
                PurchaseRequisitionLine.converted_qty, PurchaseRequisitionLine.need_date,
            )
            .join(PurchaseRequisition, PurchaseRequisitionLine.req_id == PurchaseRequisition.id)
            .where(
                PurchaseRequisition.status == "approved",
                PurchaseRequisitionLine.status.in_(["open", "partially_converted"]),
                PurchaseRequisitionLine.material_code.in_(list(mid_by_code)),
            )
        )
    ).all()
    for req_no, line_no, material_code, req_qty, converted_qty, need_date in rows:
        mid = mid_by_code.get(material_code)
        if mid is None:
            continue
        outstanding = _decimal(req_qty) - _decimal(converted_qty)
        if outstanding <= 0:
            continue
        supplies[mid].append(_supply("requisition", req_no or "", str(line_no or ""), outstanding, need_date))


async def _load_supplies(db: AsyncSession, lines: list[dict], code_to_id: dict[str, int]):
    material_ids = {ln["material_id"] for ln in lines if ln["material_id"] is not None}
    supplies: dict[int, list[dict]] = defaultdict(list)
    if not material_ids:
        return supplies
    mid_by_code = {code: mid for code, mid in code_to_id.items() if mid in material_ids}
    await _load_inventory_supplies(db, supplies, material_ids)
    await _load_purchase_order_supplies(db, supplies, mid_by_code)
    await _load_task_supplies(db, supplies, mid_by_code)
    await _load_subcontract_supplies(db, supplies, material_ids)
    await _load_transfer_supplies(db, supplies, mid_by_code)
    await _load_requisition_supplies(db, supplies, mid_by_code)
    return supplies


def _allocate_lines(lines: list[dict], supplies: dict[int, list[dict]]) -> None:
    for line in lines:
        material_id = line["material_id"]
        if material_id is None or material_id not in supplies:
            continue
        demand = _decimal(line["qty"])
        covered, allocated = _allocate_fifo(supplies[material_id], demand)
        line["supplies"] = _serialize_supplies(allocated)
        line["covered_qty"] = float(covered)
        line["shortage_qty"] = float(demand - covered)
        line["status"] = "covered" if line["shortage_qty"] <= 0 else (
            "partial" if line["covered_qty"] > 0 else "short"
        )


def _empty_result() -> dict:
    return {"order": None, "lines": [], "note": _NOTE}


def _build_result(order_no: str, lines: list[dict], total_qty: Decimal) -> dict:
    overall = "covered" if all(ln["status"] == "covered" for ln in lines) else (
        "partial" if any(ln["covered_qty"] > 0 for ln in lines) else "short"
    )
    return {
        "order": {
            "order_no": order_no,
            "lines": len(lines),
            "total_qty": float(total_qty),
            "promised_date": lines[0]["need_date"],
            "status": overall,
        },
        "lines": lines,
        "note": _NOTE,
    }


async def build_order_coverage(db: AsyncSession, order_no: str) -> dict:
    """按订单号构建覆盖视图；订单不存在或全部行已结时返回空结果（order=None）。"""
    rows = await _fetch_order_rows(db, order_no)
    if not rows:
        return _empty_result()

    snapshot = Snapshot()
    code_to_id = await _load_materials(db, snapshot)
    bom_parent = await _load_bom_parents(db)
    lines, total_qty = _build_lines(rows, bom_parent, snapshot.code_by_material, snapshot.name_by_material)
    if not lines:
        return _empty_result()

    supplies = await _load_supplies(db, lines, code_to_id)
    _allocate_lines(lines, supplies)
    return _build_result(order_no, lines, total_qty)
