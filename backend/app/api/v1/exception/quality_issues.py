"""异常与质量中心 — 品质异常 API（CRUD）"""

from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.exception.quality_issue import QualityIssue
from app.schemas.common import ResponseModel, PageResult
from app.schemas.exception.schemas import QualityIssueOut, QualityIssueCreate, QualityIssueUpdate
from app.services.common.export_service import GenericExportService, ExportColumn

router = APIRouter()


QUALITY_FILTERABLE_FIELDS = {
    "issue_no": QualityIssue.issue_no,
    "order_no": QualityIssue.order_no,
    "product_code": QualityIssue.product_code,
    "submit_dept": QualityIssue.submit_dept,
    "submit_date": QualityIssue.submit_date,
    "submitter": QualityIssue.submitter,
    "product_name": QualityIssue.product_name,
    "process": QualityIssue.process,
    "defect_type": QualityIssue.defect_type,
    "description": QualityIssue.description,
    "root_cause": QualityIssue.root_cause,
    "responsible_person": QualityIssue.responsible_person,
    "responsible_dept": QualityIssue.responsible_dept,
    "batch_qty": QualityIssue.batch_qty,
    "sample_qty": QualityIssue.sample_qty,
    "defect_qty": QualityIssue.defect_qty,
    "improvement_countermeasures": QualityIssue.improvement_countermeasures,
    "improvement_countermeasures_date": QualityIssue.improvement_countermeasures_date,
    "temporary_countermeasure": QualityIssue.temporary_countermeasure,
    "temporary_countermeasure_date": QualityIssue.temporary_countermeasure_date,
    "preliminary_analysis_person": QualityIssue.preliminary_analysis_person,
    "quality_manager_approval": QualityIssue.quality_manager_approval,
    "defect_rate": cast(QualityIssue.defect_qty, Float) / func.nullif(cast(QualityIssue.sample_qty, Float), 0),
    "status": QualityIssue.status,
    "workflow_status": QualityIssue.workflow_status,
    "created_at": QualityIssue.created_at,
    "updated_at": QualityIssue.updated_at,
}


def _resolve_quality_issue_status(data: dict, current_status: str = "open") -> str:
    improvement_date = data.get("improvement_countermeasures_date")
    if improvement_date and str(improvement_date).strip().lower() not in ("", "none", "null", "0"):
        return "closed"
    return data.get("status") or current_status or "open"


def _build_quality_conditions(
    request: Request,
    submit_dept: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
) -> list:
    conditions = []
    if submit_dept:
        conditions.append(QualityIssue.submit_dept == submit_dept)
    if status:
        conditions.append(QualityIssue.status == status)
    if keyword:
        like = f'%{keyword}%'
        conditions.append(
            QualityIssue.order_no.ilike(like)
            | QualityIssue.product_code.ilike(like)
            | QualityIssue.submit_dept.ilike(like)
            | QualityIssue.submitter.ilike(like)
            | QualityIssue.product_name.ilike(like)
            | QualityIssue.process.ilike(like)
            | QualityIssue.defect_type.ilike(like)
            | QualityIssue.description.ilike(like)
            | QualityIssue.root_cause.ilike(like)
            | QualityIssue.responsible_person.ilike(like)
            | QualityIssue.responsible_dept.ilike(like)
            | QualityIssue.improvement_countermeasures.ilike(like)
        )
    for field, column in QUALITY_FILTERABLE_FIELDS.items():
        values = request.query_params.getlist(field)
        values = [v for v in values if v not in ("", None)]
        if values:
            conditions.append(column.in_(values))
    # 软删除记录不进入列表/统计/导出
    conditions.append(QualityIssue.is_deleted == False)
    return conditions


@router.get("", response_model=ResponseModel[PageResult[QualityIssueOut]])
async def list_quality_issues(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    submit_dept: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    sort_field: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = _build_quality_conditions(request, submit_dept, status, keyword)

    count_q = select(func.count(QualityIssue.id))
    query = select(QualityIssue)
    if conditions:
        count_q = count_q.where(*conditions)
        query = query.where(*conditions)

    total = (await db.execute(count_q)).scalar()
    sort_column = QUALITY_FILTERABLE_FIELDS.get(sort_field or "")
    if sort_column is not None:
        query = query.order_by(sort_column.asc() if sort_order == "ascend" else sort_column.desc())
    else:
        query = query.order_by(QualityIssue.submit_date.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [QualityIssueOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.get("/statistics", response_model=ResponseModel[dict])
async def get_quality_issue_statistics(
    request: Request,
    submit_dept: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "read")),
    db: AsyncSession = Depends(get_db),
):
    """Return quality issue analysis stats for all rows matching current filters."""
    conditions = _build_quality_conditions(request, submit_dept, status, keyword)

    summary_q = select(
        func.count(QualityIssue.id),
        func.coalesce(func.sum(QualityIssue.defect_qty), 0),
        func.coalesce(func.sum(QualityIssue.sample_qty), 0),
    )
    if conditions:
        summary_q = summary_q.where(*conditions)
    total, total_defect_qty, total_sample_qty = (await db.execute(summary_q)).one()

    async def grouped_counts(column):
        q = select(column, func.count(QualityIssue.id)).where(column.isnot(None), column != "")
        if conditions:
            q = q.where(*conditions)
        q = q.group_by(column).order_by(func.count(QualityIssue.id).desc())
        result = await db.execute(q)
        return {str(key): count for key, count in result.all()}

    by_status = await grouped_counts(QualityIssue.status)
    by_defect_type = await grouped_counts(QualityIssue.defect_type)
    by_dept = await grouped_counts(QualityIssue.submit_dept)
    by_person = await grouped_counts(QualityIssue.responsible_person)
    avg_defect_rate = round((float(total_defect_qty or 0) / float(total_sample_qty or 0)) * 100, 2) if total_sample_qty else 0

    return ResponseModel(data={
        "total": total or 0,
        "byStatus": by_status,
        "byDefectType": by_defect_type,
        "byDept": by_dept,
        "byPerson": by_person,
        "totalDefectQty": total_defect_qty or 0,
        "totalSampleQty": total_sample_qty or 0,
        "avgDefectRate": f"{avg_defect_rate:.2f}",
        "openCount": by_status.get("open", 0),
        "inProgressCount": by_status.get("in_progress", 0),
        "closedCount": by_status.get("closed", 0),
    })


@router.post("", response_model=ResponseModel[QualityIssueOut])
async def create_quality_issue(
    data: QualityIssueCreate,
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "create")),
    db: AsyncSession = Depends(get_db),
):
    issue_date = data.submit_date or date.today()
    date_str = issue_date.strftime("%Y%m%d")
    result = await db.execute(
        select(QualityIssue.issue_no)
        .where(QualityIssue.issue_no.like(f"QI-{date_str}-%"))
        .order_by(QualityIssue.issue_no.desc())
        .limit(1)
    )
    max_issue_no = result.scalar_one_or_none()
    seq = int(max_issue_no.rsplit("-", 1)[-1]) + 1 if max_issue_no else 1
    issue_no = f"QI-{date_str}-{seq:04d}"

    issue_data = data.model_dump()
    issue_data["status"] = _resolve_quality_issue_status(issue_data)
    issue = QualityIssue(**issue_data, issue_no=issue_no)
    db.add(issue)
    await db.flush()
    await log_audit(db, "quality_issue", issue.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=QualityIssueOut.model_validate(issue))


@router.put("/{issue_id}", response_model=ResponseModel[QualityIssueOut])
async def update_quality_issue(
    issue_id: int,
    data: QualityIssueUpdate,
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(QualityIssue).where(QualityIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="品质异常不存在")

    update_data = data.model_dump(exclude_unset=True)
    update_data["status"] = _resolve_quality_issue_status(update_data, issue.status)
    await log_audit(db, "quality_issue", issue.id, "update", old_obj=issue, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(issue, field, value)

    await db.commit()
    await db.refresh(issue)
    return ResponseModel(data=QualityIssueOut.model_validate(issue))


@router.delete("/{issue_id}", response_model=ResponseModel[dict])
async def delete_quality_issue(
    issue_id: int,
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(QualityIssue).where(QualityIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="品质异常不存在")
    await log_audit(db, "quality_issue", issue.id, "delete", operator=current_user["username"])
    await db.delete(issue)
    await db.commit()
    return ResponseModel(data={"deleted": issue_id})


STATUS_LABELS = {
    'open': '待处理',
    'in_progress': '处理中',
    'closed': '已关闭',
}

EXPORT_COLUMNS = [
    ExportColumn('issue_no', '编号', 16),
    ExportColumn('order_no', '订单编号', 14),
    ExportColumn('product_code', '产品代码', 14),
    ExportColumn('submit_dept', '提出部门', 10),
    ExportColumn('submit_date', '提出日期', 12),
    ExportColumn('submitter', '提出人', 10),
    ExportColumn('product_name', '产品名称', 18),
    ExportColumn('process', '工序', 10),
    ExportColumn('defect_type', '缺陷类型', 12),
    ExportColumn('description', '异常描述', 24),
    ExportColumn('root_cause', '真实原因', 20),
    ExportColumn('responsible_person', '责任人', 10),
    ExportColumn('responsible_dept', '责任部门', 10),
    ExportColumn('batch_qty', '批量数', 10),
    ExportColumn('sample_qty', '抽样数量', 10),
    ExportColumn('defect_qty', '不良数', 10),
    ExportColumn('improvement_countermeasures', '改善对策', 20),
    ExportColumn('improvement_countermeasures_date', '改善对策日期', 14),
    ExportColumn('temporary_countermeasure', '临时对策', 16),
    ExportColumn('temporary_countermeasure_date', '临时对策时间', 14),
    ExportColumn('preliminary_analysis_person', '初步分析负责人', 14),
    ExportColumn('quality_manager_approval', '品质经理审批', 16),
    ExportColumn('status', '状态', 10),
    ExportColumn('workflow_status', '流程状态', 10),
]


@router.get("/export")
async def export_quality_issues(
    request: Request,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    submit_dept: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    sort_field: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("exceptions.quality", "read")),
    db: AsyncSession = Depends(get_db),
):
    """导出品质异常（支持筛选 + 排序，不分页）"""
    conditions = _build_quality_conditions(request, submit_dept, status, keyword)

    query = select(QualityIssue)
    if conditions:
        query = query.where(*conditions)

    sort_column = QUALITY_FILTERABLE_FIELDS.get(sort_field or "")
    if sort_column is not None:
        query = query.order_by(sort_column.asc() if sort_order == "ascend" else sort_column.desc())
    else:
        query = query.order_by(QualityIssue.submit_date.desc())

    result = await db.execute(query)
    rows = result.scalars().all()
    items = [QualityIssueOut.model_validate(r) for r in rows]

    export_rows = []
    for item in items:
        sample_qty = item.sample_qty or 0
        defect_qty = item.defect_qty or 0
        defect_rate = f'{((defect_qty / sample_qty) * 100):.2f}%' if sample_qty else ''
        export_rows.append({
            'issue_no': item.issue_no,
            'order_no': item.order_no or '',
            'product_code': item.product_code or '',
            'submit_dept': item.submit_dept or '',
            'submit_date': str(item.submit_date) if item.submit_date else '',
            'submitter': item.submitter or '',
            'product_name': item.product_name or '',
            'process': item.process or '',
            'defect_type': item.defect_type or '',
            'description': item.description or '',
            'root_cause': item.root_cause or '',
            'responsible_person': item.responsible_person or '',
            'responsible_dept': item.responsible_dept or '',
            'batch_qty': item.batch_qty if item.batch_qty is not None else '',
            'sample_qty': item.sample_qty if item.sample_qty is not None else '',
            'defect_qty': item.defect_qty if item.defect_qty is not None else '',
            'improvement_countermeasures': item.improvement_countermeasures or '',
            'improvement_countermeasures_date': str(item.improvement_countermeasures_date) if item.improvement_countermeasures_date else '',
            'temporary_countermeasure': item.temporary_countermeasure or '',
            'temporary_countermeasure_date': str(item.temporary_countermeasure_date) if item.temporary_countermeasure_date else '',
            'preliminary_analysis_person': item.preliminary_analysis_person or '',
            'quality_manager_approval': item.quality_manager_approval or '',
            'status': STATUS_LABELS.get(item.status, item.status),
            'workflow_status': item.workflow_status or '',
        })

    svc = GenericExportService(EXPORT_COLUMNS, export_rows, sheet_name='品质异常')

    if format == 'csv':
        output = svc.to_csv()
        return StreamingResponse(
            output,
            media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename=quality_issues.csv'},
        )
    else:
        output = svc.to_xlsx()
        return StreamingResponse(
            output,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename=quality_issues.xlsx'},
        )
