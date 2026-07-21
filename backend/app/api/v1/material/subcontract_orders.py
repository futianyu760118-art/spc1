"""物料齐套中心 — 委外订单 API"""

import os
import tempfile
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.material.subcontract_order import SubcontractOrder
from app.models.material.subcontract_order_detail import SubcontractOrderDetail
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.schemas import (
    SubcontractOrderOut, SubcontractOrderDetailOut,
    SubcontractOrderCreate, SubcontractOrderUpdate,
    SubcontractOrderBatchUpdate,
    SubcontractOrderDetailCreate, SubcontractOrderDetailUpdate,
)
from app.services.material.import_material_csv import import_subcontract_order_csv
from app.services.common.export_service import GenericExportService, ExportColumn

router = APIRouter()

ERP_SOURCE = "erp"
ERP_PROTECTED_FIELDS = {
    "bill_no", "bill_date", "bill_type", "supplier_id", "erp_order_id",
    "voided_flag", "closed_flag", "audit_date", "auditor_id", "settle_date",
}


def _head_to_out(head, details=None) -> SubcontractOrderOut:
    out = SubcontractOrderOut.model_validate(head)
    out.details = details
    return out


SORTABLE_COLUMNS = {
    "bill_date": SubcontractOrder.bill_date,
    "created_at": SubcontractOrder.created_at,
}


@router.get("", response_model=ResponseModel[PageResult[SubcontractOrderOut]])
async def list_subcontract_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None, description="模糊匹配 bill_no"),
    include_voided: bool = Query(False, description="是否包含 voided_flag=1 的单"),
    sort_by: Optional[str] = Query(None, description="bill_date / detail_count / total_qty / created_at"),
    sort_order: Optional[str] = Query(None, description="asc / desc"),
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = []
    if not include_voided:
        base.append((SubcontractOrder.voided_flag != 1) | SubcontractOrder.voided_flag.is_(None))
    if keyword:
        base.append(SubcontractOrder.bill_no.ilike(f"%{keyword}%"))

    total = (await db.execute(select(func.count(SubcontractOrder.id)).where(*base))).scalar() or 0

    stats_base = []
    if keyword:
        stats_base.append(SubcontractOrder.bill_no.ilike(f"%{keyword}%"))
    audited = (await db.execute(
        select(func.count(SubcontractOrder.id)).where(SubcontractOrder.status == "1", *stats_base)
    )).scalar() or 0
    pending = (await db.execute(
        select(func.count(SubcontractOrder.id)).where(
            SubcontractOrder.status.in_(["0", None, ""]), *stats_base
        )
    )).scalar() or 0
    closed = (await db.execute(
        select(func.count(SubcontractOrder.id)).where(
            SubcontractOrder.closed_flag == 1, *stats_base
        )
    )).scalar() or 0
    voided = (await db.execute(
        select(func.count(SubcontractOrder.id)).where(
            SubcontractOrder.voided_flag == 1, *stats_base
        )
    )).scalar() or 0
    stats = {"total": total, "audited": audited, "pending": pending, "closed": closed, "voided": voided}

    detail_subq = (
        select(
            SubcontractOrderDetail.erp_order_id.label("oid"),
            func.count(SubcontractOrderDetail.id).label("cnt"),
            func.sum(SubcontractOrderDetail.qty).label("qty"),
        )
        .group_by(SubcontractOrderDetail.erp_order_id)
        .subquery()
    )

    direction = "desc" if (sort_order or "desc").lower() == "desc" else "asc"
    order_clauses = []
    if sort_by == "detail_count":
        col = func.coalesce(detail_subq.c.cnt, 0)
        order_clauses.append(col.desc().nullslast() if direction == "desc" else col.asc().nullslast())
    elif sort_by == "total_qty":
        col = func.coalesce(detail_subq.c.qty, 0)
        order_clauses.append(col.desc().nullslast() if direction == "desc" else col.asc().nullslast())
    elif sort_by in SORTABLE_COLUMNS:
        col = SORTABLE_COLUMNS[sort_by]
        order_clauses.append(col.desc().nullslast() if direction == "desc" else col.asc().nullslast())
    if not order_clauses:
        order_clauses = [SubcontractOrder.bill_date.desc().nullslast(), SubcontractOrder.id.desc()]

    query = (
        select(SubcontractOrder, func.coalesce(detail_subq.c.cnt, 0), func.coalesce(detail_subq.c.qty, 0))
        .outerjoin(detail_subq, detail_subq.c.oid == SubcontractOrder.erp_order_id)
        .where(*base)
        .order_by(*order_clauses)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()
    items = []
    for head, cnt, qty in rows:
        out = SubcontractOrderOut.model_validate(head)
        out.detail_count = int(cnt or 0)
        out.total_qty = float(qty) if qty is not None else None
        items.append(out)
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items, stats=stats))


@router.post("", response_model=ResponseModel[SubcontractOrderOut])
async def create_subcontract_order(
    data: SubcontractOrderCreate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "create")),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.bill_no == data.bill_no))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"bill_no={data.bill_no} 已存在")

    head = SubcontractOrder(
        **data.model_dump(exclude={"details"}),
        data_source="manual",
    )
    db.add(head)
    await db.flush()
    head.erp_order_id = head.id  # 让两表始终能 JOIN

    created_details = []
    if data.details:
        for idx, d in enumerate(data.details, start=1):
            det = SubcontractOrderDetail(
                erp_order_id=head.erp_order_id,
                detail_id=idx,
                line_no=idx,
                data_source="manual",
                **d.model_dump(exclude_unset=True),
            )
            db.add(det)
            created_details.append(det)
        await db.flush()

    await log_audit(db, "subcontract_order", head.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(head)
    return ResponseModel(data=_head_to_out(head, [SubcontractOrderDetailOut.model_validate(d) for d in created_details]))


@router.post("/import", response_model=ResponseModel[dict])
async def import_subcontract_orders(
    file: UploadFile = File(...),
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "import")),
    db: AsyncSession = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or '')[1] or '.csv'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = await import_subcontract_order_csv(tmp_path, db)
    finally:
        os.unlink(tmp_path)
    await log_audit(db, "subcontract_order", 0, "import", field_name="csv", new_value=file.filename, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)


@router.get("/export")
async def export_subcontract_orders(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    keyword: Optional[str] = Query(None),
    include_voided: bool = Query(False),
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = []
    if not include_voided:
        base.append((SubcontractOrder.voided_flag != 1) | SubcontractOrder.voided_flag.is_(None))
    if keyword:
        base.append(SubcontractOrder.bill_no.ilike(f"%{keyword}%"))

    detail_subq = (
        select(
            SubcontractOrderDetail.erp_order_id.label("oid"),
            func.count(SubcontractOrderDetail.id).label("cnt"),
            func.sum(SubcontractOrderDetail.qty).label("qty"),
        )
        .group_by(SubcontractOrderDetail.erp_order_id)
        .subquery()
    )
    query = (
        select(SubcontractOrder, func.coalesce(detail_subq.c.cnt, 0), func.coalesce(detail_subq.c.qty, 0))
        .outerjoin(detail_subq, detail_subq.c.oid == SubcontractOrder.erp_order_id)
        .where(*base)
        .order_by(SubcontractOrder.bill_date.desc().nullslast())
    )
    rows = (await db.execute(query)).all()
    export_rows = []
    for head, cnt, qty in rows:
        export_rows.append({
            'bill_no': head.bill_no,
            'bill_date': str(head.bill_date) if head.bill_date else '',
            'bill_type': head.bill_type or '',
            'supplier_id': head.supplier_id or '',
            'status': head.status or '',
            'detail_count': int(cnt or 0),
            'total_qty': float(qty) if qty is not None else '',
            'remark': head.remark or '',
            'data_source': head.data_source or '',
        })
    svc = GenericExportService(SUBCONTRACT_EXPORT_COLUMNS, export_rows, sheet_name='委外订单')
    if format == 'csv':
        return StreamingResponse(svc.to_csv(), media_type='text/csv; charset=utf-8',
                                 headers={'Content-Disposition': 'attachment; filename=subcontract_orders.csv'})
    return StreamingResponse(svc.to_xlsx(),
                             media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             headers={'Content-Disposition': 'attachment; filename=subcontract_orders.xlsx'})


@router.put("/batch", response_model=ResponseModel[dict])
async def batch_update_subcontract_orders(
    data: SubcontractOrderBatchUpdate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    if not data.ids:
        raise HTTPException(status_code=400, detail="请选择要更新的记录")
    if data.status is None and data.remark is None:
        raise HTTPException(status_code=400, detail="请至少填写一个更新字段")
    update_fields = {k: v for k, v in {"status": data.status, "remark": data.remark}.items() if v is not None}
    result = await db.execute(
        select(SubcontractOrder).where(SubcontractOrder.id.in_(data.ids))
    )
    heads = result.scalars().all()
    for h in heads:
        for k, v in update_fields.items():
            setattr(h, k, v)
    await log_audit(
        db, "subcontract_order", 0, "batch_update",
        field_name="batch_status_remark",
        new_value=f"ids={data.ids}, {update_fields}",
        operator=current_user["username"],
    )
    await db.commit()
    return ResponseModel(data={"updated": len(heads)})


@router.get("/{order_id}", response_model=ResponseModel[SubcontractOrderOut])
async def get_subcontract_order(
    order_id: int,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    details = (
        await db.execute(
            select(SubcontractOrderDetail)
            .where(SubcontractOrderDetail.erp_order_id == head.erp_order_id)
            .order_by(SubcontractOrderDetail.line_no.asc().nullslast(), SubcontractOrderDetail.id.asc())
        )
    ).scalars().all()
    return ResponseModel(data=_head_to_out(head, [SubcontractOrderDetailOut.model_validate(d) for d in details]))


@router.get("/{order_id}/details", response_model=ResponseModel[PageResult[SubcontractOrderDetailOut]])
async def list_subcontract_order_details(
    order_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    base = [SubcontractOrderDetail.erp_order_id == head.erp_order_id]
    total = (await db.execute(select(func.count(SubcontractOrderDetail.id)).where(*base))).scalar() or 0
    rows = (
        await db.execute(
            select(SubcontractOrderDetail)
            .where(*base)
            .order_by(SubcontractOrderDetail.line_no.asc().nullslast(), SubcontractOrderDetail.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    items = [SubcontractOrderDetailOut.model_validate(r) for r in rows]
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.put("/{order_id}", response_model=ResponseModel[SubcontractOrderOut])
async def update_subcontract_order(
    order_id: int,
    data: SubcontractOrderUpdate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")

    update_data = data.model_dump(exclude_unset=True)
    if head.data_source == ERP_SOURCE:
        blocked = ERP_PROTECTED_FIELDS & update_data.keys()
        if blocked:
            raise HTTPException(
                status_code=400,
                detail=f"ERP 同步行不可修改字段: {','.join(sorted(blocked))}",
            )

    await log_audit(db, "subcontract_order", head.id, "update", old_obj=head, update_data=update_data, operator=current_user["username"])
    for k, v in update_data.items():
        setattr(head, k, v)
    await db.commit()
    await db.refresh(head)
    return ResponseModel(data=_head_to_out(head))


@router.delete("/{order_id}", response_model=ResponseModel[dict])
async def delete_subcontract_order(
    order_id: int,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "delete")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    if head.data_source == ERP_SOURCE:
        raise HTTPException(status_code=409, detail="ERP 同步行不可删除（请在 ERP 系统作废）")

    await db.execute(
        delete(SubcontractOrderDetail).where(SubcontractOrderDetail.erp_order_id == head.erp_order_id)
    )
    await log_audit(db, "subcontract_order", head.id, "delete", old_obj=head, operator=current_user["username"])
    await db.delete(head)
    await db.commit()
    return ResponseModel(data={"deleted": order_id})


@router.post("/{order_id}/details", response_model=ResponseModel[SubcontractOrderDetailOut])
async def add_subcontract_order_detail(
    order_id: int,
    data: SubcontractOrderDetailCreate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    if head.data_source == ERP_SOURCE:
        raise HTTPException(status_code=400, detail="ERP 同步单据不可添加明细")
    max_detail = (await db.execute(
        select(func.max(SubcontractOrderDetail.detail_id))
        .where(SubcontractOrderDetail.erp_order_id == head.erp_order_id)
    )).scalar() or 0
    det = SubcontractOrderDetail(
        erp_order_id=head.erp_order_id,
        detail_id=max_detail + 1,
        line_no=max_detail + 1,
        data_source="manual",
        **data.model_dump(exclude_unset=True),
    )
    db.add(det)
    await db.flush()
    await log_audit(db, "subcontract_order_detail", det.id, "create", new_value=str(data.model_dump()), operator=current_user["username"])
    await db.commit()
    await db.refresh(det)
    return ResponseModel(data=SubcontractOrderDetailOut.model_validate(det))


@router.put("/{order_id}/details/{detail_id}", response_model=ResponseModel[SubcontractOrderDetailOut])
async def update_subcontract_order_detail(
    order_id: int,
    detail_id: int,
    data: SubcontractOrderDetailUpdate,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    det = (await db.execute(
        select(SubcontractOrderDetail).where(
            SubcontractOrderDetail.erp_order_id == head.erp_order_id,
            SubcontractOrderDetail.id == detail_id,
        )
    )).scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=404, detail="明细不存在")
    if head.data_source == ERP_SOURCE or det.data_source == ERP_SOURCE:
        raise HTTPException(status_code=400, detail="ERP 同步明细不可修改")
    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "subcontract_order_detail", det.id, "update", old_obj=det, update_data=update_data, operator=current_user["username"])
    for k, v in update_data.items():
        setattr(det, k, v)
    await db.commit()
    await db.refresh(det)
    return ResponseModel(data=SubcontractOrderDetailOut.model_validate(det))


@router.delete("/{order_id}/details/{detail_id}", response_model=ResponseModel[dict])
async def delete_subcontract_order_detail(
    order_id: int,
    detail_id: int,
    current_user: dict = Depends(PermissionChecker("materials.subcontract_orders", "update")),
    db: AsyncSession = Depends(get_db),
):
    head = (await db.execute(select(SubcontractOrder).where(SubcontractOrder.id == order_id))).scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=404, detail="委外订单不存在")
    det = (await db.execute(
        select(SubcontractOrderDetail).where(
            SubcontractOrderDetail.erp_order_id == head.erp_order_id,
            SubcontractOrderDetail.id == detail_id,
        )
    )).scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=404, detail="明细不存在")
    if head.data_source == ERP_SOURCE or det.data_source == ERP_SOURCE:
        raise HTTPException(status_code=400, detail="ERP 同步明细不可删除")
    await log_audit(db, "subcontract_order_detail", det.id, "delete", old_obj=det, operator=current_user["username"])
    await db.delete(det)
    await db.commit()
    return ResponseModel(data={"deleted": detail_id})


SUBCONTRACT_EXPORT_COLUMNS = [
    ExportColumn('bill_no', '单据编号', 20),
    ExportColumn('bill_date', '日期', 12),
    ExportColumn('bill_type', '类型', 14),
    ExportColumn('supplier_id', '供应商ID', 12),
    ExportColumn('status', '状态', 14),
    ExportColumn('detail_count', '明细数', 8),
    ExportColumn('total_qty', '总数量', 12),
    ExportColumn('remark', '摘要', 30),
    ExportColumn('data_source', '数据来源', 10),
]
