"""物料齐套中心 — 采购到料计划 API"""

import tempfile
import os
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from datetime import date as date_type
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.material.purchase_order import PurchaseOrder
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import PurchaseOrderOut, PurchaseOrderCreate, PurchaseOrderUpdate, PurchasePlanStats
from app.services.material.import_material_csv import import_purchase_plan_csv

router = APIRouter()


SORTABLE_COLUMNS = {
    'supplier_name': PurchaseOrder.supplier_name,
    'material_code': PurchaseOrder.material_code,
    'material_name': PurchaseOrder.material_name,
    'spec_model': PurchaseOrder.spec_model,
    'po_date': PurchaseOrder.po_date,
    'po_qty': PurchaseOrder.po_qty,
    'received_qty': PurchaseOrder.received_qty,
    'eta': PurchaseOrder.eta,
    'order_no': PurchaseOrder.order_no,
    'actual_arrival_date': PurchaseOrder.actual_arrival_date,
    'inspection_date': PurchaseOrder.inspection_date,
    'owner': PurchaseOrder.owner,
}


@router.get("", response_model=ResponseModel[PageResult[PurchaseOrderOut]])
async def list_purchase_plan(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    supplier_name: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    po_status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = []

    if supplier_name:
        base.append(PurchaseOrder.supplier_name.ilike(f'%{supplier_name}%'))
    if order_no:
        base.append(PurchaseOrder.order_no.ilike(f'%{order_no}%'))
    today = date_type.today()
    if po_status:
        # 支持逗号分隔的多个状态值
        status_list = [s.strip() for s in po_status.split(',')]
        status_conditions = []
        stagnant_filter = False
        for s in status_list:
            if s == 'stagnant':
                stagnant_filter = True
            elif s == 'inspected':
                status_conditions.append(PurchaseOrder.inspection_date.isnot(None))
            elif s == 'arrived':
                status_conditions.append(
                    PurchaseOrder.actual_arrival_date.isnot(None)
                    & PurchaseOrder.inspection_date.is_(None)
                )
            elif s == 'overdue':
                status_conditions.append(
                    PurchaseOrder.inspection_date.is_(None)
                    & PurchaseOrder.actual_arrival_date.is_(None)
                    & PurchaseOrder.eta.isnot(None)
                    & (PurchaseOrder.eta < today)
                )
            elif s == 'pending':
                status_conditions.append(
                    PurchaseOrder.inspection_date.is_(None)
                    & PurchaseOrder.actual_arrival_date.is_(None)
                    & or_(PurchaseOrder.eta.is_(None), PurchaseOrder.eta >= today)
                )
        if stagnant_filter:
            base.append(
                PurchaseOrder.received_qty.isnot(None)
                & PurchaseOrder.po_qty.isnot(None)
                & (PurchaseOrder.received_qty > PurchaseOrder.po_qty)
            )
        if status_conditions:
            base.append(or_(*status_conditions))
    else:
        # 当没有筛选状态时，排除po_status为NULL的记录
        base.append(PurchaseOrder.po_status.isnot(None))
    if keyword:
        like = f'%{keyword}%'
        base.append(
            PurchaseOrder.material_code.ilike(like)
            | PurchaseOrder.material_name.ilike(like)
            | PurchaseOrder.supplier_name.ilike(like)
            | PurchaseOrder.order_no.ilike(like)
        )

    total_result = await db.execute(select(func.count(PurchaseOrder.id)).where(*base))
    total = total_result.scalar()

    # 构建排序子句
    order_clauses = []
    if sort_by and sort_by in SORTABLE_COLUMNS:
        col = SORTABLE_COLUMNS[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    # 默认排序
    if not order_clauses:
        order_clauses = [PurchaseOrder.eta.asc().nullslast(), PurchaseOrder.updated_at.desc()]

    query = (
        select(PurchaseOrder)
        .where(*base)
        .order_by(*order_clauses)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    rows = result.scalars().all()
    # 实时重算状态（不落库），保证 overdue 等依赖当天日期的状态展示正确
    for r in rows:
        if r.inspection_date:
            r.po_status = 'inspected'
        elif r.actual_arrival_date:
            r.po_status = 'arrived'
        elif r.eta and r.eta < today:
            r.po_status = 'overdue'
        else:
            r.po_status = 'pending'
    items = []
    for r in rows:
        out = PurchaseOrderOut.model_validate(r)
        # 呆滞物料判定：收料数量 > 下单数量
        if r.received_qty is not None and r.po_qty is not None and r.received_qty > r.po_qty:
            out.is_stagnant = True
            out.stagnant_qty = float(r.received_qty - r.po_qty)
        items.append(out)

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[PurchaseOrderOut])
async def create_purchase_plan(
    data: PurchaseOrderCreate,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "create")),
    db: AsyncSession = Depends(get_db),
):
    po = PurchaseOrder(**data.model_dump(), data_source='csv_plan')
    db.add(po)
    await db.flush()
    await log_audit(db, "purchase_order", po.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(po)
    return ResponseModel(data=PurchaseOrderOut.model_validate(po))


@router.put("/{record_id}", response_model=ResponseModel[PurchaseOrderOut])
async def update_purchase_plan(
    record_id: int,
    data: PurchaseOrderUpdate,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == record_id))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "purchase_order", po.id, "update", old_obj=po, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(po, field, value)

    # 重新计算状态
    today = date_type.today()
    if po.inspection_date:
        po.po_status = 'inspected'
    elif po.actual_arrival_date:
        po.po_status = 'arrived'
    elif po.eta and po.eta < today:
        po.po_status = 'overdue'
    else:
        po.po_status = 'pending'
    await db.commit()
    await db.refresh(po)
    return ResponseModel(data=PurchaseOrderOut.model_validate(po))


@router.post("/import", response_model=ResponseModel[dict])
async def import_purchase_plan(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "import")),
    db: AsyncSession = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or '')[1] or '.csv'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await import_purchase_plan_csv(tmp_path, db)
    finally:
        os.unlink(tmp_path)

    await log_audit(db, "purchase_order", 0, "import", field_name="purchase_plan_csv", new_value=file.filename, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)


@router.get("/stats", response_model=ResponseModel[PurchasePlanStats])
async def get_purchase_plan_stats(
    supplier_name: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    po_status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    """获取采购计划统计（支持筛选）"""
    today = date_type.today()
    base = []

    if supplier_name:
        base.append(PurchaseOrder.supplier_name.ilike(f'%{supplier_name}%'))
    if order_no:
        base.append(PurchaseOrder.order_no.ilike(f'%{order_no}%'))
    stagnant_filter = False
    if po_status:
        # 支持逗号分隔的多个状态值
        status_list = [s.strip() for s in po_status.split(',')]
        status_conditions = []
        for s in status_list:
            if s == 'stagnant':
                stagnant_filter = True
            elif s == 'inspected':
                status_conditions.append(PurchaseOrder.inspection_date.isnot(None))
            elif s == 'arrived':
                status_conditions.append(
                    PurchaseOrder.actual_arrival_date.isnot(None)
                    & PurchaseOrder.inspection_date.is_(None)
                )
            elif s == 'overdue':
                status_conditions.append(
                    PurchaseOrder.inspection_date.is_(None)
                    & PurchaseOrder.actual_arrival_date.is_(None)
                    & PurchaseOrder.eta.isnot(None)
                    & (PurchaseOrder.eta < today)
                )
            elif s == 'pending':
                status_conditions.append(
                    PurchaseOrder.inspection_date.is_(None)
                    & PurchaseOrder.actual_arrival_date.is_(None)
                    & or_(PurchaseOrder.eta.is_(None), PurchaseOrder.eta >= today)
                )
        if stagnant_filter:
            base.append(
                PurchaseOrder.received_qty.isnot(None)
                & PurchaseOrder.po_qty.isnot(None)
                & (PurchaseOrder.received_qty > PurchaseOrder.po_qty)
            )
        if status_conditions:
            base.append(or_(*status_conditions))
    else:
        base.append(PurchaseOrder.po_status.isnot(None))
    if keyword:
        like = f'%{keyword}%'
        base.append(
            PurchaseOrder.material_code.ilike(like)
            | PurchaseOrder.material_name.ilike(like)
            | PurchaseOrder.supplier_name.ilike(like)
            | PurchaseOrder.order_no.ilike(like)
        )

    # 总数
    total_result = await db.execute(select(func.count(PurchaseOrder.id)).where(*base))
    total = total_result.scalar() or 0

    # 已检验
    inspected_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(PurchaseOrder.inspection_date.isnot(None), *base)
    )
    inspected = inspected_result.scalar() or 0

    # 已到料（已到料但未检验）
    arrived_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.actual_arrival_date.isnot(None),
            PurchaseOrder.inspection_date.is_(None),
            *base
        )
    )
    arrived = arrived_result.scalar() or 0

    # 逾期未到
    overdue_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.inspection_date.is_(None),
            PurchaseOrder.actual_arrival_date.is_(None),
            PurchaseOrder.eta.isnot(None),
            PurchaseOrder.eta < today,
            *base
        )
    )
    overdue = overdue_result.scalar() or 0

    # 待到料（未到料且未逾期）
    pending_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.inspection_date.is_(None),
            PurchaseOrder.actual_arrival_date.is_(None),
            or_(PurchaseOrder.eta.is_(None), PurchaseOrder.eta >= today),
            *base
        )
    )
    pending = pending_result.scalar() or 0

    # 呆滞物料（收料数量 > 下单数量）
    stagnant_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.received_qty.isnot(None),
            PurchaseOrder.po_qty.isnot(None),
            PurchaseOrder.received_qty > PurchaseOrder.po_qty,
            *base
        )
    )
    stagnant = stagnant_result.scalar() or 0

    return ResponseModel(data=PurchasePlanStats(
        total=total,
        pending=pending,
        arrived=arrived,
        inspected=inspected,
        overdue=overdue,
        stagnant=stagnant,
    ))
