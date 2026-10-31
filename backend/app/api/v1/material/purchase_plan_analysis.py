"""采购到料计划 — 分析图表 API"""

from datetime import date as date_type, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.supplier_scope import get_supplier_name_scope
from app.models.material.purchase_order import PurchaseOrder
from app.schemas.common import ResponseModel
from app.api.v1.material.purchase_plan import _build_filters

router = APIRouter()

STATUS_COLORS = {
    'pending': '#94a3b8',
    'partial_received': '#f59e0b',
    'fully_received': '#16a34a',
    'overdue': '#e11d48',
}

STATUS_LABELS = {
    'pending': '待到料',
    'partial_received': '部分到',
    'fully_received': '已到齐',
    'overdue': '逾期未到',
}


@router.get("", response_model=ResponseModel)
async def get_purchase_plan_analysis(
    supplier_name: Optional[str] = Query(None),
    supplier_account: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    po_status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    material_code: Optional[str] = Query(None),
    material_name: Optional[str] = Query(None),
    material_property: Optional[int] = Query(None),
    spec_model: Optional[str] = Query(None),
    unit: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    arrival_hour_note: Optional[str] = Query(None),
    po_date_start: Optional[str] = Query(None),
    po_date_end: Optional[str] = Query(None),
    eta_start: Optional[str] = Query(None),
    eta_end: Optional[str] = Query(None),
    actual_arrival_start: Optional[str] = Query(None),
    actual_arrival_end: Optional[str] = Query(None),
    inspection_start: Optional[str] = Query(None),
    inspection_end: Optional[str] = Query(None),
    po_qty_min: Optional[float] = Query(None),
    po_qty_max: Optional[float] = Query(None),
    received_qty_min: Optional[float] = Query(None),
    received_qty_max: Optional[float] = Query(None),
    only_shortage: Optional[bool] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    today = date_type.today()
    supplier_scope = await get_supplier_name_scope(current_user, db)
    base = _build_filters(
        None if supplier_scope else supplier_name, supplier_account, order_no, po_status, keyword,
        material_code=material_code, material_name=material_name,
        material_property=material_property, spec_model=spec_model, unit=unit, owner=owner,
        arrival_hour_note=arrival_hour_note,
        po_date_start=po_date_start, po_date_end=po_date_end,
        eta_start=eta_start, eta_end=eta_end,
        actual_arrival_start=actual_arrival_start, actual_arrival_end=actual_arrival_end,
        inspection_start=inspection_start, inspection_end=inspection_end,
        po_qty_min=po_qty_min, po_qty_max=po_qty_max,
        received_qty_min=received_qty_min, received_qty_max=received_qty_max,
        only_shortage=only_shortage,
    )
    if supplier_scope:
        base.append(PurchaseOrder.supplier_name == supplier_scope)

    status_distribution = []
    no_received = or_(PurchaseOrder.received_qty.is_(None), PurchaseOrder.received_qty == 0)
    for status_key, label in STATUS_LABELS.items():
        cond = base.copy()
        if status_key == 'fully_received':
            cond.append(PurchaseOrder.received_qty > 0)
            cond.append(PurchaseOrder.po_qty.isnot(None))
            cond.append(PurchaseOrder.received_qty >= PurchaseOrder.po_qty)
        elif status_key == 'partial_received':
            cond.append(PurchaseOrder.received_qty > 0)
            cond.append(or_(
                PurchaseOrder.po_qty.is_(None),
                PurchaseOrder.received_qty < PurchaseOrder.po_qty,
            ))
        elif status_key == 'overdue':
            cond.append(no_received)
            cond.append(PurchaseOrder.eta.isnot(None))
            cond.append(PurchaseOrder.eta < today)
            cond.append(PurchaseOrder.is_closed == 0)
        elif status_key == 'pending':
            cond.append(no_received)
            cond.append(or_(PurchaseOrder.eta.is_(None), PurchaseOrder.eta >= today))
            cond.append(PurchaseOrder.is_closed == 0)
        count_result = await db.execute(select(func.count(PurchaseOrder.id)).where(*cond))
        count = count_result.scalar() or 0
        status_distribution.append({
            'name': label,
            'value': count,
            'color': STATUS_COLORS.get(status_key, '#94a3b8'),
        })

    supplier_overdue_top5 = await _get_supplier_overdue(db, base, today)
    material_shortage_top5 = await _get_material_shortage(db, base)

    return ResponseModel(data={
        'status_distribution': status_distribution,
        'supplier_overdue_top5': supplier_overdue_top5,
        'material_shortage_top5': material_shortage_top5,
    })


async def _get_supplier_overdue(db: AsyncSession, base: list, today: date_type):
    overdue_base = base.copy()
    overdue_base.append(or_(PurchaseOrder.received_qty.is_(None), PurchaseOrder.received_qty == 0))
    overdue_base.append(PurchaseOrder.eta.isnot(None))
    overdue_base.append(PurchaseOrder.eta < today)
    overdue_base.append(PurchaseOrder.is_closed == 0)

    result = await db.execute(
        select(
            PurchaseOrder.supplier_name,
            func.count(PurchaseOrder.id).label('cnt')
        )
        .where(*overdue_base)
        .group_by(PurchaseOrder.supplier_name)
        .order_by(func.count(PurchaseOrder.id).desc())
        .limit(5)
    )
    return [
        {'name': row.supplier_name or '未知', 'value': row.cnt}
        for row in result.all()
    ]


async def _get_material_shortage(db: AsyncSession, base: list):
    shortage_base = base.copy()
    shortage_base.append(
        PurchaseOrder.po_qty.isnot(None)
        & (
            PurchaseOrder.received_qty.is_(None)
            | (PurchaseOrder.po_qty > PurchaseOrder.received_qty)
        )
    )

    result = await db.execute(
        select(
            PurchaseOrder.material_code,
            PurchaseOrder.material_name,
            func.sum(
                func.coalesce(PurchaseOrder.po_qty, 0) - func.coalesce(PurchaseOrder.received_qty, 0)
            ).label('total_shortage')
        )
        .where(*shortage_base)
        .group_by(PurchaseOrder.material_code, PurchaseOrder.material_name)
        .order_by(func.sum(
            func.coalesce(PurchaseOrder.po_qty, 0) - func.coalesce(PurchaseOrder.received_qty, 0)
        ).desc())
        .limit(5)
    )
    return [
        {
            'name': row.material_name or row.material_code,
            'value': round(float(row.total_shortage), 1),
        }
        for row in result.all()
    ]