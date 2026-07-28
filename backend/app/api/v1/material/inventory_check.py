"""物料齐套中心 — 订单物料盘点 API"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.schemas.material.schemas import (
    InventoryCheckOut,
    InventoryCheckListOut,
    InventoryCheckCreate,
    MaterialSnapshotItem,
)
from app.models.material.order_inventory_check import OrderInventoryCheck
from app.services.material.kit_analysis_service import get_order_materials, get_kit_analysis

router = APIRouter()


def _build_snapshot(materials: list) -> List[MaterialSnapshotItem]:
    snapshots = []
    for m in materials:
        snapshots.append(MaterialSnapshotItem(
            material_code=m.material_code,
            material_name=m.material_name,
            status=m.status,
            bom_demand_qty=m.bom_demand_qty,
            stock_qty=m.stock_qty,
            available_stock_qty=m.available_stock_qty,
            transit_qty=getattr(m, "transit_qty", None),
            po_qty=m.po_qty,
            received_qty=m.received_qty,
            shortage_qty=m.shortage_qty,
            supplier_name=m.supplier_name,
            po_no=m.po_no,
            eta=m.eta,
            bill_type=m.bill_type,
            bill_type_label=m.bill_type_label,
            material_property=m.material_property,
            material_property_label=m.material_property_label,
        ))
    return snapshots


@router.post("/orders/{order_no}/inventory-check", response_model=ResponseModel[InventoryCheckOut])
async def create_inventory_check(
    order_no: str,
    body: InventoryCheckCreate,
    current_user: dict = Depends(PermissionChecker("orders.inventory_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    materials = await get_order_materials(db, order_no=order_no)
    kit = await get_kit_analysis(db, order_no=order_no, page=1, page_size=1)

    kit_item = kit["items"][0] if kit["items"] else None
    total = len(materials)
    received = kit_item.received_materials if kit_item else 0
    partial = kit_item.partial_received_materials if kit_item else 0
    not_ordered = kit_item.not_ordered_materials if kit_item else 0
    overdue = kit_item.overdue_materials if kit_item else 0
    kit_rate_val = kit_item.kit_rate if kit_item else 0
    snapshot = _build_snapshot(materials)

    check = OrderInventoryCheck(
        order_no=order_no,
        checked_by=current_user.get("username", ""),
        checked_at=datetime.utcnow(),
        total_materials=total,
        received_materials=received,
        partial_received_materials=partial,
        not_ordered_materials=not_ordered,
        overdue_materials=overdue,
        kit_rate=kit_rate_val,
        materials_snapshot=[s.model_dump() for s in snapshot],
        note=body.note,
    )
    db.add(check)
    await db.commit()
    await db.refresh(check)
    return ResponseModel(data=InventoryCheckOut.model_validate(check))


@router.get("/orders/{order_no}/inventory-check/latest", response_model=ResponseModel[Optional[InventoryCheckOut]])
async def latest_inventory_check(
    order_no: str,
    current_user: dict = Depends(PermissionChecker("orders.inventory_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrderInventoryCheck)
        .where(OrderInventoryCheck.order_no == order_no)
        .order_by(desc(OrderInventoryCheck.checked_at))
        .limit(1)
    )
    check = result.scalar_one_or_none()
    return ResponseModel(data=InventoryCheckOut.model_validate(check) if check else None)


@router.get("/orders/{order_no}/inventory-check/history", response_model=ResponseModel[List[InventoryCheckListOut]])
async def order_inventory_check_history(
    order_no: str,
    current_user: dict = Depends(PermissionChecker("orders.inventory_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrderInventoryCheck)
        .where(OrderInventoryCheck.order_no == order_no)
        .order_by(desc(OrderInventoryCheck.checked_at))
    )
    checks = result.scalars().all()
    return ResponseModel(data=[InventoryCheckListOut.model_validate(c) for c in checks])


@router.get("/orders/{order_no}/inventory-check/{check_id}", response_model=ResponseModel[InventoryCheckOut])
async def get_inventory_check_detail(
    order_no: str,
    check_id: int,
    current_user: dict = Depends(PermissionChecker("orders.inventory_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrderInventoryCheck)
        .where(OrderInventoryCheck.id == check_id, OrderInventoryCheck.order_no == order_no)
    )
    check = result.scalar_one_or_none()
    if not check:
        raise HTTPException(status_code=404, detail="盘点记录不存在")
    return ResponseModel(data=InventoryCheckOut.model_validate(check))


@router.get("/inventory-check/recent", response_model=ResponseModel[List[InventoryCheckListOut]])
async def recent_inventory_checks(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(PermissionChecker("orders.inventory_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrderInventoryCheck)
        .order_by(desc(OrderInventoryCheck.checked_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    checks = result.scalars().all()
    return ResponseModel(data=[InventoryCheckListOut.model_validate(c) for c in checks])
