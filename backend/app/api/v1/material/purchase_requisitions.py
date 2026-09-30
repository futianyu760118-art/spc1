"""物料齐套中心 — 采购申请单 API"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import PageResult, ResponseModel
from app.schemas.material.purchase_requisition import (
    ConvertToPoRequest,
    RequisitionCreateRequest,
    RequisitionDetailOut,
    RequisitionOut,
    RequisitionUpdateRequest,
)
from app.services.common.export_service import ExportColumn, GenericExportService
from app.services.material.purchase_requisition_service import (
    PurchaseRequisitionService,
    RequisitionNotFoundError,
    RequisitionStateError,
)

router = APIRouter()

STATUS_LABELS = {
    "draft": "草稿",
    "approving": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
    "closed": "已关闭",
}

LINE_STATUS_LABELS = {
    "open": "未转单",
    "partially_converted": "部分转单",
    "closed": "已转单",
}

SOURCE_LABELS = {
    "manual": "手工",
    "mrp": "MRP",
    "excel": "Excel",
}

EXPORT_COLUMNS = [
    ExportColumn("req_no", "申请单号", 24),
    ExportColumn("status", "单据状态", 10),
    ExportColumn("applicant", "申请人", 10),
    ExportColumn("department", "部门", 14),
    ExportColumn("source", "来源", 10),
    ExportColumn("submitted_at", "提交时间", 18),
    ExportColumn("line_no", "行号", 6),
    ExportColumn("material_code", "物料编码", 22),
    ExportColumn("material_name", "物料名称", 18),
    ExportColumn("spec_model", "规格型号", 20),
    ExportColumn("unit", "单位", 8),
    ExportColumn("req_qty", "申请数量", 10),
    ExportColumn("need_date", "到货日期", 12),
    ExportColumn("supplier_name", "建议供应商", 24),
    ExportColumn("unit_price", "参考单价", 12),
    ExportColumn("converted_qty", "已转数量", 10),
    ExportColumn("converted_po_no", "转单号", 24),
    ExportColumn("line_status", "行状态", 12),
    ExportColumn("remark", "备注", 18),
]


def _raise_value_error(exc: ValueError) -> None:
    """服务层 ValueError：单据不存在 → 404，状态冲突 → 409，其余业务校验 → 400。"""
    if isinstance(exc, RequisitionNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RequisitionStateError):
        raise HTTPException(status_code=409, detail=str(exc))
    raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=ResponseModel[PageResult[RequisitionOut]])
async def list_requisitions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    applicant: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    date_start: Optional[str] = Query(None),
    date_end: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.purchase_requisition", "read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        total, items = await PurchaseRequisitionService().list_requisitions(
            db, page=page, page_size=page_size, keyword=keyword, status=status,
            applicant=applicant, source=source, date_start=date_start, date_end=date_end,
        )
    except ValueError as exc:
        _raise_value_error(exc)
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[RequisitionDetailOut])
async def create_requisition(
    data: RequisitionCreateRequest,
    current_user: dict = Depends(PermissionChecker("materials.purchase_requisition", "create")),
    db: AsyncSession = Depends(get_db),
):
    """手工新建采购申请单（draft）。"""
    username = current_user.get("username") or "system"
    service = PurchaseRequisitionService()
    try:
        req = await service.create_requisition(
            db, applicant=username, department=data.department,
            lines=[line.model_dump() for line in data.lines], remark=data.remark,
        )
    except ValueError as exc:
        _raise_value_error(exc)
    await log_audit(db, "purchase_requisition", req.id, "create", operator=username)
    return ResponseModel(data=await service.get_detail(db, req.id), message="创建成功")


@router.get("/{req_id}", response_model=ResponseModel[RequisitionDetailOut])
async def get_requisition(
    req_id: int,
    current_user: dict = Depends(PermissionChecker("materials.purchase_requisition", "read")),
    db: AsyncSession = Depends(get_db),
):
    detail = await PurchaseRequisitionService().get_detail(db, req_id)
    if not detail:
        raise HTTPException(status_code=404, detail="采购申请单不存在")
    return ResponseModel(data=detail)


@router.put("/{req_id}", response_model=ResponseModel[RequisitionDetailOut])
async def update_requisition(
    req_id: int,
    data: RequisitionUpdateRequest,
    current_user: dict = Depends(PermissionChecker("materials.purchase_requisition", "update")),
    db: AsyncSession = Depends(get_db),
):
    """编辑采购申请单：仅 draft/rejected；传 lines 时明细整体替换。"""
    service = PurchaseRequisitionService()
    try:
        await service.update_requisition(
            db, req_id, data.model_dump(exclude_unset=True),
            current_user.get("username") or "system",
        )
    except ValueError as exc:
        _raise_value_error(exc)
    return ResponseModel(data=await service.get_detail(db, req_id), message="保存成功")


@router.post("/{req_id}/submit", response_model=ResponseModel[RequisitionDetailOut])
async def submit_requisition(
    req_id: int,
    current_user: dict = Depends(PermissionChecker("materials.purchase_requisition", "update")),
    db: AsyncSession = Depends(get_db),
):
    """提交审批：仅 draft/rejected；审批链未配置时返回 400。"""
    try:
        detail = await PurchaseRequisitionService().submit(
            db, req_id, current_user.get("username") or "system"
        )
    except ValueError as exc:
        _raise_value_error(exc)
    return ResponseModel(data=detail, message="提交成功")


@router.post("/{req_id}/convert-to-po", response_model=ResponseModel[dict])
async def convert_requisition_to_po(
    req_id: int,
    data: ConvertToPoRequest,
    current_user: dict = Depends(PermissionChecker("materials.purchase_requisition", "convert")),
    db: AsyncSession = Depends(get_db),
):
    """将审批通过的申请单行按数量转换为 SPC 采购订单。"""
    username = current_user.get("username") or "system"
    try:
        result = await PurchaseRequisitionService().convert_to_po(
            db, req_id=req_id, username=username,
            items=[item.model_dump() for item in data.items],
        )
    except ValueError as exc:
        _raise_value_error(exc)
    await log_audit(
        db, "purchase_requisition", req_id, "convert_to_po",
        new_value=f"created={result['created']}, closed={result['closed']}", operator=username,
    )
    return ResponseModel(data=result, message="转采购订单成功")


@router.get("/{req_id}/export")
async def export_requisition(
    req_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    current_user: dict = Depends(PermissionChecker("materials.purchase_requisition", "read")),
    db: AsyncSession = Depends(get_db),
):
    """导出单张采购申请单（表头 + 明细行展开）。"""
    try:
        rows = await PurchaseRequisitionService().export_rows(db, req_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    export_rows = [{
        "req_no": row["req_no"],
        "status": STATUS_LABELS.get(row["status"], row["status"]),
        "applicant": row.get("applicant") or "",
        "department": row.get("department") or "",
        "source": SOURCE_LABELS.get(row.get("source"), row.get("source") or ""),
        "submitted_at": row.get("submitted_at") or "",
        "line_no": row["line_no"],
        "material_code": row["material_code"],
        "material_name": row.get("material_name") or "",
        "spec_model": row.get("spec_model") or "",
        "unit": row.get("unit") or "",
        "req_qty": row["req_qty"],
        "need_date": row.get("need_date") or "",
        "supplier_name": row.get("supplier_name") or "",
        "unit_price": row.get("unit_price") if row.get("unit_price") is not None else "",
        "converted_qty": row["converted_qty"],
        "converted_po_no": row.get("converted_po_no") or "",
        "line_status": LINE_STATUS_LABELS.get(row["line_status"], row["line_status"]),
        "remark": row.get("remark") or "",
    } for row in rows]

    svc = GenericExportService(EXPORT_COLUMNS, export_rows, sheet_name="采购申请单")
    if format == "csv":
        return StreamingResponse(
            svc.to_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=purchase_requisition.csv"},
        )
    return StreamingResponse(
        svc.to_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=purchase_requisition.xlsx"},
    )
