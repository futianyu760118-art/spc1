"""MRP 例外：列表 / 批量处理 / 导出。"""

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.mrp.suggestions import _resolve_run_id
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.material.purchase_requisition import PurchaseRequisition, PurchaseRequisitionLine
from app.models.mrp.exception import MrpException
from app.models.mrp.suggestion import MrpSuggestion
from app.schemas.common import PageResult, ResponseModel
from app.schemas.mrp.schemas import BatchHandleRequest, MrpExceptionOut
from app.services.common.export_service import ExportColumn, GenericExportService
from app.services.material.purchase_requisition_service import PurchaseRequisitionService
from app.services.order.eta_service import update_purchase_order_eta

logger = logging.getLogger(__name__)

exceptions_router = APIRouter()

# 引擎写库用短名（po/requisition），模型注释与设计文档用全名，两者兼容
PO_SOURCE_TYPES = ("po", "purchase_order")
REQUISITION_SOURCE_TYPES = ("requisition", "purchase_requisition")
REQUISITION_LINE_EDITABLE = ("open", "partially_converted")
NOTIFY_EXCEPTION_TYPES = ("past_due_supply", "supply_late")
LATE_EXCEPTION_TYPES = ("supply_late", "supply_early")

EXCEPTION_TYPE_LABELS = {
    "past_due_demand": "拖期需求",
    "past_due_supply": "拖期供给",
    "supply_late": "建议提前",
    "supply_early": "建议延后",
    "supply_excess": "取消或减量",
    "below_safety_stock": "低于安全库存",
    "no_bom": "无有效BOM",
}

SOURCE_TYPE_LABELS = {
    "po": "采购订单",
    "purchase_order": "采购订单",
    "task": "生产任务",
    "production_task_order": "生产任务",
    "subcontract": "委外",
    "subcontract_order": "委外",
    "transfer": "调拨",
    "transfer_order": "调拨",
    "requisition": "采购申请",
    "purchase_requisition": "采购申请",
    "sale_order_line": "销售订单",
    "mrp_material": "物料",
}

STATUS_LABELS = {"open": "待处理", "resolved": "已处理", "ignored": "已忽略"}

HANDLE_ACTION_LABELS = {
    "ignore": "忽略",
    "reschedule": "改期",
    "cancel_reduce": "取消或减量",
    "notify": "催货",
}

EXPORT_COLUMNS = [
    ExportColumn("material_code", "物料编码", 22),
    ExportColumn("material_name", "物料名称", 18),
    ExportColumn("exception_type", "例外类型", 14),
    ExportColumn("source_type", "源单据类型", 12),
    ExportColumn("source_doc_no", "源单据号", 20),
    ExportColumn("source_line_no", "源单据行号", 12),
    ExportColumn("need_date", "需求日", 12),
    ExportColumn("doc_date", "单据日期", 12),
    ExportColumn("adjust_days", "调整天数", 10),
    ExportColumn("suggest_date", "建议日期", 12),
    ExportColumn("suggest_qty", "建议数量", 12),
    ExportColumn("detail", "描述", 40),
    ExportColumn("status", "状态", 10),
    ExportColumn("handle_action", "处理动作", 12),
    ExportColumn("handled_by", "处理人", 12),
    ExportColumn("handled_at", "处理时间", 18),
]


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _list_conditions(*, run_id: int, exception_type: Optional[str] = None,
                     status: Optional[str] = None, source_type: Optional[str] = None,
                     only_late: bool = False, keyword: Optional[str] = None) -> list:
    """列表与导出共用同一筛选口径。"""
    conditions = [MrpException.run_id == run_id]
    if exception_type:
        conditions.append(MrpException.exception_type == exception_type)
    if status:
        conditions.append(MrpException.status == status)
    if source_type:
        conditions.append(MrpException.source_type == source_type)
    if only_late:
        conditions.append(MrpException.exception_type.in_(LATE_EXCEPTION_TYPES))
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            MrpException.material_code.ilike(like) | MrpException.material_name.ilike(like)
        )
    return conditions


@exceptions_router.get("/exceptions", response_model=ResponseModel[PageResult[MrpExceptionOut]])
async def list_exceptions(
    run_id: Optional[int] = Query(None),
    exception_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    only_late: bool = Query(False),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    resolved_run_id = await _resolve_run_id(db, run_id)
    conditions = _list_conditions(
        run_id=resolved_run_id, exception_type=exception_type, status=status,
        source_type=source_type, only_late=only_late, keyword=keyword,
    )
    total = (
        await db.execute(select(func.count()).select_from(MrpException).where(*conditions))
    ).scalar() or 0
    rows = (
        await db.execute(
            select(MrpException)
            .where(*conditions)
            .order_by(MrpException.exception_code, MrpException.material_code, MrpException.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    # stats 为同批次全量口径（不受状态/类型/来源/关键词筛选影响），供前端 chips 计数
    stats_conditions = _list_conditions(run_id=resolved_run_id)
    by_status_rows = (
        await db.execute(
            select(MrpException.status, func.count())
            .where(*stats_conditions)
            .group_by(MrpException.status)
        )
    ).all()
    by_type_rows = (
        await db.execute(
            select(MrpException.exception_type, func.count())
            .where(*stats_conditions)
            .group_by(MrpException.exception_type)
        )
    ).all()
    return ResponseModel(
        data=PageResult(
            total=int(total), page=page, page_size=page_size,
            items=[MrpExceptionOut.model_validate(r) for r in rows],
            stats={
                "by_status": {key: int(count) for key, count in by_status_rows},
                "by_type": {key: int(count) for key, count in by_type_rows},
            },
        )
    )


@exceptions_router.get("/exceptions/export")
async def export_exceptions(
    run_id: Optional[int] = Query(None),
    exception_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    only_late: bool = Query(False),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    """导出例外清单（CSV，筛选口径与列表一致，不分页）。"""
    resolved_run_id = await _resolve_run_id(db, run_id)
    conditions = _list_conditions(
        run_id=resolved_run_id, exception_type=exception_type, status=status,
        source_type=source_type, only_late=only_late, keyword=keyword,
    )
    rows = (await db.execute(
        select(MrpException)
        .where(*conditions)
        .order_by(MrpException.exception_code, MrpException.material_code, MrpException.id)
    )).scalars().all()
    export_rows = [{
        "material_code": r.material_code,
        "material_name": r.material_name or "",
        "exception_type": EXCEPTION_TYPE_LABELS.get(r.exception_type, r.exception_type),
        "source_type": SOURCE_TYPE_LABELS.get(r.source_type, r.source_type),
        "source_doc_no": r.source_doc_no or "",
        "source_line_no": r.source_line_no or "",
        "need_date": _fmt(r.need_date),
        "doc_date": _fmt(r.doc_date),
        "adjust_days": r.adjust_days if r.adjust_days is not None else "",
        "suggest_date": _fmt(r.suggest_date),
        "suggest_qty": float(r.suggest_qty) if r.suggest_qty is not None else "",
        "detail": r.detail or "",
        "status": STATUS_LABELS.get(r.status, r.status),
        "handle_action": HANDLE_ACTION_LABELS.get(r.handle_action or "", r.handle_action or ""),
        "handled_by": r.handled_by or "",
        "handled_at": _fmt(r.handled_at),
    } for r in rows]
    svc = GenericExportService(EXPORT_COLUMNS, export_rows, sheet_name="MRP例外")
    return StreamingResponse(
        svc.to_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=mrp_exceptions.csv"},
    )


async def _require_requisition_line(db: AsyncSession, exc: MrpException) -> PurchaseRequisitionLine:
    """定位申请单明细行并校验可操作；不可操作时抛 ValueError（计入 skipped）。"""
    if exc.source_id is None:
        raise ValueError("例外缺少源单据行 ID，无法定位采购申请明细")
    line = (
        await db.execute(
            select(PurchaseRequisitionLine).where(PurchaseRequisitionLine.id == exc.source_id)
        )
    ).scalar_one_or_none()
    if line is None:
        raise ValueError("采购申请明细不存在")
    if line.status not in REQUISITION_LINE_EDITABLE:
        raise ValueError(f"采购申请明细状态为 {line.status}，不可操作")
    req_status = (
        await db.execute(
            select(PurchaseRequisition.status).where(PurchaseRequisition.id == line.req_id)
        )
    ).scalar_one_or_none()
    if req_status != "approved":
        raise ValueError("采购申请单已不在审批通过状态，不可操作")
    return line


async def _apply_action(db: AsyncSession, exc: MrpException, *, action: str, username: str) -> None:
    """执行动作矩阵的副作用；来源不支持或数据不可操作时抛 ValueError。"""
    if action == "reschedule":
        if exc.suggest_date is None:
            raise ValueError("无建议日期")
        if exc.source_type in PO_SOURCE_TYPES:
            if exc.source_id is not None:
                await update_purchase_order_eta(
                    db, po_id=exc.source_id, new_eta=exc.suggest_date,
                    updater=username, update_reason="MRP 例外改期",
                )
                return
            if not exc.source_doc_no:
                raise ValueError("例外缺少源单据号，无法定位采购订单")
            try:
                detail_id = int(exc.source_line_no)
            except (TypeError, ValueError):
                raise ValueError("例外缺少源单据行号，无法定位采购订单明细")
            await update_purchase_order_eta(
                db, po_no=exc.source_doc_no, detail_id=detail_id, new_eta=exc.suggest_date,
                updater=username, update_reason="MRP 例外改期",
            )
            return
        if exc.source_type in REQUISITION_SOURCE_TYPES:
            line = await _require_requisition_line(db, exc)
            line.need_date = exc.suggest_date
            return
        raise ValueError(f"来源类型 {exc.source_type} 不支持改期")
    if action == "cancel_reduce":
        if exc.source_type in REQUISITION_SOURCE_TYPES:
            line = await _require_requisition_line(db, exc)
            await PurchaseRequisitionService().close_line_and_maybe_header(db, line)
            if line.source_suggestion_id is not None:
                await db.execute(
                    update(MrpSuggestion)
                    .where(
                        MrpSuggestion.id == line.source_suggestion_id,
                        MrpSuggestion.status == "converted",
                    )
                    .values(status="rejected")
                )
            return
        raise ValueError(f"来源类型 {exc.source_type} 不支持取消或减量")
    if action == "notify":
        if exc.exception_type not in NOTIFY_EXCEPTION_TYPES:
            raise ValueError("该类型不支持催货")
        return


@exceptions_router.post("/exceptions/batch-handle", response_model=ResponseModel[dict])
async def batch_handle_exceptions(
    payload: BatchHandleRequest,
    current_user: dict = Depends(PermissionChecker("materials.mrp", "review")),
    db: AsyncSession = Depends(get_db),
):
    """批量处理例外：逐条 SAVEPOINT 隔离，单条失败/来源不支持不影响其它条目。"""
    username = current_user.get("username")
    updated = 0
    skipped: list[dict] = []
    for exception_id in payload.exception_ids:
        savepoint = await db.begin_nested()
        try:
            exc = (
                await db.execute(select(MrpException).where(MrpException.id == exception_id))
            ).scalar_one_or_none()
            if exc is None:
                await savepoint.rollback()
                skipped.append({"id": exception_id, "reason": "例外不存在"})
                continue
            if exc.status != "open":
                await savepoint.rollback()
                skipped.append({"id": exception_id, "reason": f"例外状态为 {exc.status}，不可处理"})
                continue
            await _apply_action(db, exc, action=payload.action, username=username)
            if payload.action == "ignore":
                exc.status = "ignored"
            elif payload.action in ("reschedule", "cancel_reduce"):
                exc.status = "resolved"
            exc.handle_action = payload.action
            exc.handled_by = username
            exc.handled_at = datetime.now()
            await savepoint.commit()
            updated += 1
        except ValueError as exc_err:
            await savepoint.rollback()
            skipped.append({"id": exception_id, "reason": str(exc_err)})
        except Exception as exc_err:  # 单条异常不拖垮整批（SAVEPOINT 回滚后外层事务仍可用）
            logger.warning("MRP 例外批量处理异常 id=%s: %s", exception_id, exc_err)
            await savepoint.rollback()
            skipped.append({"id": exception_id, "reason": "系统异常，请稍后重试"})
    return ResponseModel(data={"updated": updated, "skipped": skipped})
