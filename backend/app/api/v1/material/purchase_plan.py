"""物料齐套中心 — 采购到料计划 API"""

import tempfile
import os
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from datetime import date as date_type
from sqlalchemy import select, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.core.supplier_scope import get_supplier_name_scope
from app.models.material.purchase_order import PurchaseOrder
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import PurchaseOrderOut, PurchaseOrderCreate, PurchaseOrderUpdate, PurchaseOrderBatchUpdate, PurchasePlanStats
from app.services.material.import_material_csv import import_purchase_plan_csv
from app.services.common.export_service import GenericExportService, ExportColumn
from app.services.common.sync_filter import get_purchase_order_sync_filters

router = APIRouter()


SORTABLE_COLUMNS = {
    'supplier_name': PurchaseOrder.supplier_name,
    'supplier_account': PurchaseOrder.supplier_account,
    'material_code': PurchaseOrder.material_code,
    'material_name': PurchaseOrder.material_name,
    'material_property': PurchaseOrder.material_property,
    'spec_model': PurchaseOrder.spec_model,
    'po_date': PurchaseOrder.po_date,
    'po_qty': PurchaseOrder.po_qty,
    'received_qty': PurchaseOrder.received_qty,
    'original_eta': PurchaseOrder.original_eta,
    'eta': PurchaseOrder.eta,
    'order_no': PurchaseOrder.order_no,
    'actual_arrival_date': PurchaseOrder.actual_arrival_date,
    'inspection_date': PurchaseOrder.inspection_date,
    'owner': PurchaseOrder.owner,
    'is_closed': PurchaseOrder.is_closed,
    'is_stagnant': PurchaseOrder.received_qty,  # 呆滞按收料数量排序
    'po_status': PurchaseOrder.po_status,
}


STATUS_LABELS = {
    'fully_received': '已到齐',
    'partial_received': '部分到',
    'overdue': '逾期未到',
    'pending': '待到料',
}

EXPORT_COLUMNS = [
    ExportColumn('supplier_name', '供应商', 16),
    ExportColumn('supplier_account', '供应商账号', 18),
    ExportColumn('material_code', '物料长代码', 20),
    ExportColumn('material_name', '物料名称', 18),
    ExportColumn('material_property', '物料属性', 10),
    ExportColumn('spec_model', '规格型号', 20),
    ExportColumn('unit', '单位', 8),
    ExportColumn('po_date', '下单日期', 12),
    ExportColumn('po_qty', '数量', 10),
    ExportColumn('received_qty', '收料数量', 10),
    ExportColumn('original_eta', '同步交货日期', 12),
    ExportColumn('eta', '交货日期', 12),
    ExportColumn('order_no', '订单号', 14),
    ExportColumn('actual_arrival_date', '到料时间', 12),
    ExportColumn('arrival_hour_note', '小时节点', 14),
    ExportColumn('inspection_date', '检验日期', 12),
    ExportColumn('owner', '责任人', 10),
    ExportColumn('po_status', '状态', 10),
    ExportColumn('is_closed', '关闭', 8),
    ExportColumn('is_stagnant', '呆滞', 8),
]


def _build_filters(
    supplier_name: Optional[str],
    supplier_account: Optional[str],
    order_no: Optional[str],
    po_status: Optional[str],
    keyword: Optional[str],
    material_code: Optional[str] = None,
    material_name: Optional[str] = None,
    material_property: Optional[int] = None,
    spec_model: Optional[str] = None,
    unit: Optional[str] = None,
    owner: Optional[str] = None,
    arrival_hour_note: Optional[str] = None,
    po_date_start: Optional[str] = None,
    po_date_end: Optional[str] = None,
    eta_start: Optional[str] = None,
    eta_end: Optional[str] = None,
    actual_arrival_start: Optional[str] = None,
    actual_arrival_end: Optional[str] = None,
    inspection_start: Optional[str] = None,
    inspection_end: Optional[str] = None,
    po_qty_min: Optional[float] = None,
    po_qty_max: Optional[float] = None,
    received_qty_min: Optional[float] = None,
    received_qty_max: Optional[float] = None,
    only_shortage: Optional[bool] = None,
    is_closed: Optional[str] = None,
) -> list:
    """构建采购到料计划通用筛选条件列表"""
    base = []
    today = date_type.today()

    if supplier_name:
        base.append(PurchaseOrder.supplier_name.ilike(f'%{supplier_name}%'))
    if supplier_account:
        base.append(PurchaseOrder.supplier_account.ilike(f'%{supplier_account}%'))
    if order_no:
        base.append(PurchaseOrder.order_no.ilike(f'%{order_no}%'))
    if material_code:
        base.append(PurchaseOrder.material_code.ilike(f'%{material_code}%'))
    if material_name:
        base.append(PurchaseOrder.material_name.ilike(f'%{material_name}%'))
    if material_property is not None:
        base.append(PurchaseOrder.material_property == material_property)
    if spec_model:
        base.append(PurchaseOrder.spec_model.ilike(f'%{spec_model}%'))
    if unit:
        base.append(PurchaseOrder.unit.ilike(f'%{unit}%'))
    if owner:
        base.append(PurchaseOrder.owner.ilike(f'%{owner}%'))
    if arrival_hour_note:
        base.append(PurchaseOrder.arrival_hour_note.ilike(f'%{arrival_hour_note}%'))
    if po_date_start:
        base.append(PurchaseOrder.po_date >= date_type.fromisoformat(po_date_start))
    if po_date_end:
        base.append(PurchaseOrder.po_date <= date_type.fromisoformat(po_date_end))
    if eta_start:
        base.append(PurchaseOrder.eta >= date_type.fromisoformat(eta_start))
    if eta_end:
        base.append(PurchaseOrder.eta <= date_type.fromisoformat(eta_end))
    if actual_arrival_start:
        base.append(PurchaseOrder.actual_arrival_date >= date_type.fromisoformat(actual_arrival_start))
    if actual_arrival_end:
        base.append(PurchaseOrder.actual_arrival_date <= date_type.fromisoformat(actual_arrival_end))
    if inspection_start:
        base.append(PurchaseOrder.inspection_date >= date_type.fromisoformat(inspection_start))
    if inspection_end:
        base.append(PurchaseOrder.inspection_date <= date_type.fromisoformat(inspection_end))
    if po_qty_min is not None:
        base.append(PurchaseOrder.po_qty >= po_qty_min)
    if po_qty_max is not None:
        base.append(PurchaseOrder.po_qty <= po_qty_max)
    if received_qty_min is not None:
        base.append(PurchaseOrder.received_qty >= received_qty_min)
    if received_qty_max is not None:
        base.append(PurchaseOrder.received_qty <= received_qty_max)
    if only_shortage:
        base.append(
            PurchaseOrder.po_qty.isnot(None)
            & (
                PurchaseOrder.received_qty.is_(None)
                | (PurchaseOrder.po_qty > PurchaseOrder.received_qty)
            )
        )
    if po_status:
        status_list = [s.strip() for s in po_status.split(',')]
        status_conditions = []
        stagnant_filter = False
        for s in status_list:
            if s == 'stagnant':
                stagnant_filter = True
            elif s == 'fully_received':
                status_conditions.append(
                    (PurchaseOrder.received_qty > 0)
                    & PurchaseOrder.po_qty.isnot(None)
                    & (PurchaseOrder.received_qty >= PurchaseOrder.po_qty)
                )
            elif s == 'partial_received':
                status_conditions.append(
                    (PurchaseOrder.received_qty > 0)
                    & or_(
                        PurchaseOrder.po_qty.is_(None),
                        PurchaseOrder.received_qty < PurchaseOrder.po_qty,
                    )
                )
            elif s == 'overdue':
                status_conditions.append(
                    or_(PurchaseOrder.received_qty.is_(None), PurchaseOrder.received_qty == 0)
                    & PurchaseOrder.eta.isnot(None)
                    & (PurchaseOrder.eta < today)
                )
            elif s == 'pending':
                status_conditions.append(
                    or_(PurchaseOrder.received_qty.is_(None), PurchaseOrder.received_qty == 0)
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
    if is_closed:
        closed_list = [s.strip() for s in is_closed.split(',')]
        closed_conditions = []
        for s in closed_list:
            if s == 'closed':
                closed_conditions.append(PurchaseOrder.is_closed == 1)
            elif s == 'open':
                closed_conditions.append(PurchaseOrder.is_closed == 0)
        if closed_conditions:
            base.append(or_(*closed_conditions))
    return base


def _build_order_clauses(sort_by: Optional[str], sort_order: Optional[str]) -> list:
    """构建排序子句"""
    order_clauses = []
    if sort_by and sort_by in SORTABLE_COLUMNS:
        col = SORTABLE_COLUMNS[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    if not order_clauses:
        order_clauses = [PurchaseOrder.eta.asc().nullslast(), PurchaseOrder.updated_at.desc()]
    return order_clauses


def _recalc_status(row):
    """实时重算状态（不落库），纯按收料数量推导；已到料状态已移除"""
    today = date_type.today()
    if row.received_qty is not None and row.received_qty > 0:
        if row.po_qty is not None and row.received_qty >= row.po_qty:
            row.po_status = 'fully_received'
        else:
            row.po_status = 'partial_received'
    elif row.eta and row.eta < today:
        row.po_status = 'overdue'
    else:
        row.po_status = 'pending'


def _to_export_item(r) -> PurchaseOrderOut:
    """将 ORM 行转为 PurchaseOrderOut 并补充呆滞/缺料字段"""
    _recalc_status(r)
    out = PurchaseOrderOut.model_validate(r)
    if r.received_qty is not None and r.po_qty is not None and r.received_qty > r.po_qty:
        out.is_stagnant = True
        out.stagnant_qty = float(r.received_qty - r.po_qty)
    # 计算缺料差异：po_qty - received_qty，正数表示缺料
    if r.po_qty is not None:
        received = float(r.received_qty) if r.received_qty is not None else 0.0
        diff = float(r.po_qty) - received
        if diff > 0:
            out.shortage_qty = diff
    return out


@router.get("", response_model=ResponseModel[PageResult[PurchaseOrderOut]])
async def list_purchase_plan(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    supplier_name: Optional[str] = Query(None),
    supplier_account: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    po_status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
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
    is_closed: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    sync_filters = await get_purchase_order_sync_filters(db)
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
        is_closed=is_closed,
    )
    base.extend(sync_filters)
    if supplier_scope:
        base.append(PurchaseOrder.supplier_name == supplier_scope)

    total_result = await db.execute(select(func.count(PurchaseOrder.id)).where(*base))
    total = total_result.scalar()

    order_clauses = _build_order_clauses(sort_by, sort_order)

    query = (
        select(PurchaseOrder)
        .where(*base)
        .order_by(*order_clauses)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    rows = result.scalars().all()
    items = [_to_export_item(r) for r in rows]

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


@router.put("/batch", response_model=ResponseModel[dict])
async def batch_update_purchase_plan(
    data: PurchaseOrderBatchUpdate,
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "update")),
    db: AsyncSession = Depends(get_db),
):
    """批量更新采购到料计划，支持交货时间/责任人/供应商账号/到料时间/检验日期，支持清空字段。"""
    if not data.ids:
        raise HTTPException(status_code=400, detail="请选择要更新的记录")
    if (
        data.eta is None
        and data.owner is None
        and data.supplier_account is None
        and data.actual_arrival_date is None
        and data.inspection_date is None
        and data.is_closed is None
        and not data.clear_fields
    ):
        raise HTTPException(status_code=400, detail="请至少填写一个更新字段")

    # 构建更新字段
    update_fields: dict = {}
    if data.eta is not None:
        update_fields['eta'] = data.eta
    if data.owner is not None:
        update_fields['owner'] = data.owner
    if data.supplier_account is not None:
        update_fields['supplier_account'] = data.supplier_account
    if data.actual_arrival_date is not None:
        update_fields['actual_arrival_date'] = data.actual_arrival_date
    if data.inspection_date is not None:
        update_fields['inspection_date'] = data.inspection_date
    if data.is_closed is not None:
        update_fields['is_closed'] = data.is_closed

    allowed_clear_fields = {'eta', 'owner', 'supplier_account', 'actual_arrival_date', 'inspection_date'}
    if data.clear_fields:
        for f in data.clear_fields:
            if f in allowed_clear_fields:
                update_fields[f] = None

    # 批量更新
    stmt = (
        update(PurchaseOrder)
        .where(PurchaseOrder.id.in_(data.ids))
        .values(**update_fields)
    )
    result = await db.execute(stmt)
    updated_count = result.rowcount

    # 如果更新了状态相关字段，需要重新计算状态
    if (
        data.eta is not None
        or data.actual_arrival_date is not None
        or data.inspection_date is not None
        or data.is_closed is not None
        or getattr(data, 'received_qty', None) is not None
        or getattr(data, 'po_qty', None) is not None
        or (data.clear_fields and any(f in {'eta', 'actual_arrival_date', 'inspection_date', 'received_qty', 'po_qty'} for f in data.clear_fields))
    ):
        rows_result = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.id.in_(data.ids))
        )
        for po in rows_result.scalars().all():
            _recalc_status(po)

    await log_audit(db, "purchase_order", 0, "batch_update",
                    field_name="batch_eta_owner",
                    new_value=(
                        f"ids={data.ids}, eta={data.eta}, owner={data.owner}, "
                        f"supplier_account={data.supplier_account}, actual_arrival_date={data.actual_arrival_date}, "
                        f"inspection_date={data.inspection_date}, clear_fields={data.clear_fields}"
                    ),
                    operator=current_user["username"])
    await db.commit()
    return ResponseModel(data={"updated": updated_count})


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
    _recalc_status(po)
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


@router.get("/export")
async def export_purchase_plan(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    supplier_name: Optional[str] = Query(None),
    supplier_account: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    po_status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
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
    is_closed: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    """导出采购到料计划（支持筛选 + 排序，不分页）"""
    supplier_scope = await get_supplier_name_scope(current_user, db)
    sync_filters = await get_purchase_order_sync_filters(db)
    base = _build_filters(
        None if supplier_scope else supplier_name, supplier_account, order_no, po_status, keyword,
        material_code=material_code, material_name=material_name,
        material_property=material_property,
        spec_model=spec_model, unit=unit, owner=owner,
        arrival_hour_note=arrival_hour_note,
        po_date_start=po_date_start, po_date_end=po_date_end,
        eta_start=eta_start, eta_end=eta_end,
        actual_arrival_start=actual_arrival_start, actual_arrival_end=actual_arrival_end,
        inspection_start=inspection_start, inspection_end=inspection_end,
        po_qty_min=po_qty_min, po_qty_max=po_qty_max,
        received_qty_min=received_qty_min, received_qty_max=received_qty_max,
        only_shortage=only_shortage,
        is_closed=is_closed,
    )
    base.extend(sync_filters)
    if supplier_scope:
        base.append(PurchaseOrder.supplier_name == supplier_scope)
    order_clauses = _build_order_clauses(sort_by, sort_order)

    query = select(PurchaseOrder).where(*base).order_by(*order_clauses)
    result = await db.execute(query)
    rows = result.scalars().all()
    items = [_to_export_item(r) for r in rows]

    export_rows = []
    for item in items:
        export_rows.append({
            'supplier_name': item.supplier_name or '',
            'material_code': item.material_code,
            'material_name': item.material_name or '',
            'spec_model': item.spec_model or '',
            'unit': item.unit or '',
            'po_date': str(item.po_date) if item.po_date else '',
            'po_qty': item.po_qty if item.po_qty is not None else '',
            'received_qty': item.received_qty if item.received_qty is not None else '',
            'original_eta': str(item.original_eta) if item.original_eta else '',
            'eta': str(item.eta) if item.eta else '',
            'order_no': item.order_no or '',
            'actual_arrival_date': str(item.actual_arrival_date) if item.actual_arrival_date else '',
            'arrival_hour_note': item.arrival_hour_note or '',
            'inspection_date': str(item.inspection_date) if item.inspection_date else '',
            'owner': item.owner or '',
            'po_status': STATUS_LABELS.get(item.po_status, item.po_status),
            'is_closed': '已关闭' if item.is_closed == 1 else '',
            'is_stagnant': f'呆滞 +{item.stagnant_qty}' if item.is_stagnant else '',
        })

    svc = GenericExportService(EXPORT_COLUMNS, export_rows, sheet_name='采购到料计划')

    if format == 'csv':
        output = svc.to_csv()
        return StreamingResponse(
            output,
            media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename=purchase_plan.csv'},
        )
    else:
        output = svc.to_xlsx()
        return StreamingResponse(
            output,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename=purchase_plan.xlsx'},
        )


@router.get("/stats", response_model=ResponseModel[PurchasePlanStats])
async def get_purchase_plan_stats(
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
    is_closed: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_plan", "read")),
    db: AsyncSession = Depends(get_db),
):
    """获取采购计划统计（支持筛选）"""
    today = date_type.today()
    supplier_scope = await get_supplier_name_scope(current_user, db)
    sync_filters = await get_purchase_order_sync_filters(db)
    base = _build_filters(
        None if supplier_scope else supplier_name, supplier_account, order_no, po_status, keyword,
        material_code=material_code, material_name=material_name,
        material_property=material_property,
        spec_model=spec_model, unit=unit, owner=owner,
        arrival_hour_note=arrival_hour_note,
        po_date_start=po_date_start, po_date_end=po_date_end,
        eta_start=eta_start, eta_end=eta_end,
        actual_arrival_start=actual_arrival_start, actual_arrival_end=actual_arrival_end,
        inspection_start=inspection_start, inspection_end=inspection_end,
        po_qty_min=po_qty_min, po_qty_max=po_qty_max,
        received_qty_min=received_qty_min, received_qty_max=received_qty_max,
        only_shortage=only_shortage,
        is_closed=is_closed,
    )
    base.extend(sync_filters)
    if supplier_scope:
        base.append(PurchaseOrder.supplier_name == supplier_scope)

    # 总数
    total_result = await db.execute(select(func.count(PurchaseOrder.id)).where(*base))
    total = total_result.scalar() or 0

    # 部分到（0 < 收料 < 订单）
    partial_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            (PurchaseOrder.received_qty > 0)
            & or_(
                PurchaseOrder.po_qty.is_(None),
                PurchaseOrder.received_qty < PurchaseOrder.po_qty,
            ),
            *base
        )
    )
    partial_received = partial_result.scalar() or 0

    # 已到齐（收料 >= 订单）
    fully_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            (PurchaseOrder.received_qty > 0)
            & PurchaseOrder.po_qty.isnot(None)
            & (PurchaseOrder.received_qty >= PurchaseOrder.po_qty),
            *base
        )
    )
    fully_received = fully_result.scalar() or 0

    # 逾期未到（无收料，且 eta 超期）
    overdue_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            or_(PurchaseOrder.received_qty.is_(None), PurchaseOrder.received_qty == 0),
            PurchaseOrder.eta.isnot(None),
            PurchaseOrder.eta < today,
            *base
        )
    )
    overdue = overdue_result.scalar() or 0

    # 待到料（无收料，未逾期）
    pending_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            or_(PurchaseOrder.received_qty.is_(None), PurchaseOrder.received_qty == 0),
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

    # 已关闭
    closed_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.is_closed == 1,
            *base
        )
    )
    closed = closed_result.scalar() or 0

    return ResponseModel(data=PurchasePlanStats(
        total=total,
        pending=pending,
        partial_received=partial_received,
        fully_received=fully_received,
        overdue=overdue,
        stagnant=stagnant,
        closed=closed,
    ))
