"""生产协同对外接口（AEOS 生产协同中心只读接入，P0+P1）

数据源仅现有表：
- work-orders  ← production_task_order（OA 生产任务单）
- operations   ← process_progress（工序进度统一模型；SPC 无工单级工序，order_no 必填）
- order-links  ← production_task_order（订单级）+ production_order_schedule_snapshot（行级），link_type 区分
- reports      ← production_daily_report（ERP 生产日报）
- capacity     ← production_capacity_slot + production_base_condition 按（部门, 排产段, 日期）聚合

契约无来源的字段恒返回 null，不虚构；状态映射为建议口径（待生产负责人 D0 签认），status_raw 保留源语义。
任务单不冗余订单号（production_task_order.sale_order_no 生产库全空），work-orders / order-links
的 order_no 输出与 order_no 过滤一律经 sale_order.erp_id = production_task_order.sale_order_id
解析（同 stock_check / front_process 口径）。
data_as_of = 源表全表 max(updated_at)（非过滤集），空过滤结果仍携带真实刷新时间；源表无任何行时
回退该表同步类型的最近成功同步时间（sync_sql_config.last_sync_time）或 CSV 导入时间（audit_log），
皆无则返回 code=503 结构化错误。data_confidence 仅 high/medium/low，不使用请求时间兜底。
工序表（process_progress）无行时以生产任务单同步时间（production_task_orders，生产协同数据域基线）
兜底：数据源已成功同步，空结果照常返回真实时效且不判过期。

时效口径（2026-09-24 AEOS 确认）：
- 工序/报工/产能为历史快照基线（计划/累计报工/已排产能），有 data_as_of 即 stale=false，
  置信度仅 high（≤6h）/ medium，不按 24h 判过期；无任何数据源返回 code=503 结构化错误。
- 工单/工单-订单关系仍按 6h/24h 实时口径如实返回 stale。
"""

from datetime import date, datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.basicdata.audit_log import AuditLog
from app.models.basicdata.data_supply import DataSupplyApiKey
from app.models.order.sale_order import SaleOrder
from app.models.production.base_condition import ProductionBaseCondition
from app.models.production.capacity_slot import CapacitySlot
from app.models.production.order_schedule_snapshot import ProductionOrderScheduleSnapshot
from app.models.production.process_progress import ProcessProgress
from app.models.production.production_daily_report import ProductionDailyReport
from app.models.production.production_task_order import ProductionTaskOrder
from app.schemas.common import ResponseModel
from app.services.material.kitting_calc_service import load_source_as_of, min_as_of

from ..common import ExternalDataPage, PageParamsMixin
from ..deps import external_auth
from ..freshness import freshness_meta, table_max_as_of
from ..log_wrap import log_external_call
from ..registry import register_external

router = APIRouter(prefix="/production", tags=["生产协同"])

WO_TASK_STATUS_DOC = "标准状态 planned/released/in_progress/completed/unknown（cancelled 无来源永不产出）"


def _d(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _n(value) -> Optional[float]:
    return float(value) if value is not None else None


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _page(q) -> tuple[int, int]:
    page = max(q.page or 1, 1)
    page_size = min(max(q.page_size if q.page_size is not None else 20, 1), 200)
    return page, page_size


async def _latest_import_at(db: AsyncSession, *table_names: str) -> Optional[datetime]:
    """CSV 导入最近一次发生时间（audit_log action='import'）：源表全空时的真实回退时间源。"""
    return (await db.execute(
        select(func.max(AuditLog.operated_at)).where(
            AuditLog.table_name.in_(table_names), AuditLog.action == "import",
        )
    )).scalar()


async def _freshness(
    db: AsyncSession, *columns, sync_types: tuple[str, ...] = (),
    import_tables: tuple[str, ...] = (), baseline: bool = False,
) -> dict:
    """生产协同时效元信息：源表全表 max → 同步时间 → 导入时间回退；全空 → code=503 结构化错误。

    baseline=True（工序/报工/产能：历史快照即有效基线，24h 过期口径不适用）：
    有数据时置信度仅 high（≤6h）/ medium，stale 恒 false；全空同样返回结构化错误。
    """
    as_of = await table_max_as_of(db, *columns)
    if as_of is None and sync_types:
        as_of = min_as_of(await load_source_as_of(db, sync_types))
    if as_of is None and import_tables:
        as_of = await _latest_import_at(db, *import_tables)
    return freshness_meta(as_of, "生产协同", baseline=baseline)


# ---------------------------------------------------------------- work-orders

def _map_task_status(row: ProductionTaskOrder) -> tuple[Optional[str], str]:
    """(status_raw, status)：is_closed 优先于开工标志；标志全空视为 unknown，不猜测。"""
    if row.is_closed == 1:
        return "closed", "completed"
    if row.start_flag == 1 or row.actual_start_date is not None:
        return "started", "in_progress"
    if row.audit_status == 1:
        return "audited_not_started", "released"
    if row.is_closed is None and row.start_flag is None and row.audit_status is None:
        return None, "unknown"
    return "not_started", "planned"


def _wo_status_condition(statuses: list[str]):
    """标准状态 → 源表标志位的 DB 层等价条件（保证 total/分页正确）。"""
    m = ProductionTaskOrder
    closed = m.is_closed == 1
    not_closed = or_(m.is_closed.is_(None), m.is_closed != 1)
    started = or_(m.start_flag == 1, m.actual_start_date.isnot(None))
    # NULL 三值逻辑下 ~started 不可靠（start_flag IS NULL 时为 NULL），须显式枚举未开工
    not_started = and_(
        or_(m.start_flag.is_(None), m.start_flag != 1), m.actual_start_date.is_(None),
    )
    flags_all_null = and_(
        m.is_closed.is_(None), m.start_flag.is_(None), m.audit_status.is_(None),
    )
    branch = {
        "completed": closed,
        "in_progress": and_(not_closed, started),
        "released": and_(not_closed, not_started, m.audit_status == 1),
        "planned": and_(not_closed, not_started, ~flags_all_null,
                        or_(m.audit_status.is_(None), m.audit_status != 1)),
        "unknown": and_(flags_all_null, not_started),
    }
    return or_(*(branch[s] for s in statuses if s in branch))


def _order_no_filter(order_no: str):
    """order_no 精确匹配：主口径经 sale_order.erp_id 解析（任务单 sale_order_no 生产库全空），
    保留已回填值的兼容匹配。"""
    resolved_ids = select(SaleOrder.erp_id).where(SaleOrder.order_no == order_no)
    return or_(
        ProductionTaskOrder.sale_order_no == order_no,
        ProductionTaskOrder.sale_order_id.in_(resolved_ids),
    )


def _task_orders_with_order_no():
    """任务单行 + 解析出的销售订单号（sale_order.erp_id = task.sale_order_id，同 stock_check 口径）。"""
    return (
        select(ProductionTaskOrder, SaleOrder.order_no)
        .outerjoin(SaleOrder, SaleOrder.erp_id == ProductionTaskOrder.sale_order_id)
    )


def _serialize_task_order(row: ProductionTaskOrder, order_no: Optional[str] = None) -> dict:
    status_raw, status = _map_task_status(row)
    return {
        "work_order_id": str(row.id),
        "work_order_no": row.task_no,
        "source_system": row.data_source,
        "org_code": row.workshop,
        "product_code": row.material_code,
        "product_name": row.material_name,
        "bom_id": str(row.bom_id) if row.bom_id is not None else None,
        "bom_version": None,
        "planned_qty": _n(row.task_qty),
        "uom": None,
        "completed_qty": _n(row.actual_qty),
        "good_qty": None,
        "scrap_qty": None,
        "repair_qty": _n(row.repair_qty),
        "received_qty": None,
        "status_raw": status_raw,
        "status": status,
        "planned_start_at": _d(row.planned_start_date),
        "planned_end_at": _d(row.planned_end_date),
        "actual_start_at": _d(row.actual_start_date),
        "actual_end_at": _d(row.actual_end_date),
        "estimated_finish_at": None,
        "schedule_version": None,
        "workshop_code": row.workshop,
        "owner_org": row.workshop,
        "owner": None,
        "blocking": None,
        "blocking_reason": None,
        "order_no": order_no or row.sale_order_no,
        "sale_order_id": row.sale_order_id,
        "task_type": row.task_type,
        "task_id": row.task_id,
        "start_flag": row.start_flag,
        "is_closed": row.is_closed,
        "audit_status": row.audit_status,
        "erp_updated_at": _d(row.erp_updated_at),
        "updated_at": _d(row.updated_at),
    }


class WorkOrderOut(BaseModel):
    work_order_id: str
    work_order_no: Optional[str] = None
    source_system: Optional[str] = None
    org_code: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    bom_id: Optional[str] = None
    bom_version: Optional[str] = None
    planned_qty: Optional[float] = None
    uom: Optional[str] = None
    completed_qty: Optional[float] = None
    good_qty: Optional[float] = None
    scrap_qty: Optional[float] = None
    repair_qty: Optional[float] = None
    received_qty: Optional[float] = None
    status_raw: Optional[str] = None
    status: str = "unknown"
    planned_start_at: Optional[str] = None
    planned_end_at: Optional[str] = None
    actual_start_at: Optional[str] = None
    actual_end_at: Optional[str] = None
    estimated_finish_at: Optional[str] = None
    schedule_version: Optional[str] = None
    workshop_code: Optional[str] = None
    owner_org: Optional[str] = None
    owner: Optional[str] = None
    blocking: Optional[bool] = None
    blocking_reason: Optional[str] = None
    order_no: Optional[str] = None
    sale_order_id: Optional[int] = None
    task_type: Optional[str] = None
    task_id: Optional[int] = None
    start_flag: Optional[int] = None
    is_closed: Optional[int] = None
    audit_status: Optional[int] = None
    erp_updated_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkOrdersListQuery(PageParamsMixin):
    work_order_no: Optional[str] = Field(None, description="任务单号精确匹配")
    order_no: Optional[str] = Field(None, description="销售订单号精确匹配")
    product_code: Optional[str] = Field(None, description="物料代码精确匹配")
    status: Optional[str] = Field(None, description=f"标准状态逗号分隔多选；{WO_TASK_STATUS_DOC}")
    workshop: Optional[str] = Field(None, description="生产车间精确匹配")
    planned_end_start: Optional[date] = Field(None, description="计划完工日期起 YYYY-MM-DD（含）")
    planned_end_end: Optional[date] = Field(None, description="计划完工日期止 YYYY-MM-DD（含）")
    updated_after: Optional[datetime] = Field(None, description="增量同步，仅返回 updated_at >= 此时间的记录（ISO 8601）")
    request_id: Optional[str] = Field(None, description="调用方请求 ID（回显）")


@router.get("/work-orders/list", response_model=ResponseModel[ExternalDataPage[WorkOrderOut]],
            summary="生产工单列表", description="endpoint_code: production.work_orders.list")
@register_external(
    "production.work_orders.list", "生产工单列表", method="GET", path="/production/work-orders/list",
    description="OA 生产任务单快照（工单等价物）；数量口径 task_qty/actual_qty/repair_qty；状态映射待 D0 签认",
    tags=["生产协同"],
)
@log_external_call("production.work_orders.list")
async def production_work_orders_list(
    request: Request,
    q: Annotated[WorkOrdersListQuery, Query()],
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("production.work_orders.list")),
):
    page, page_size = _page(q)
    conditions = []
    if q.work_order_no:
        conditions.append(ProductionTaskOrder.task_no == q.work_order_no)
    if q.order_no:
        conditions.append(_order_no_filter(q.order_no))
    if q.product_code:
        conditions.append(ProductionTaskOrder.material_code == q.product_code)
    if q.workshop:
        conditions.append(ProductionTaskOrder.workshop == q.workshop)
    if q.status:
        statuses = [s.strip() for s in q.status.split(",") if s.strip()]
        if statuses:
            conditions.append(_wo_status_condition(statuses))
    if q.planned_end_start:
        conditions.append(ProductionTaskOrder.planned_end_date >= q.planned_end_start)
    if q.planned_end_end:
        conditions.append(ProductionTaskOrder.planned_end_date <= q.planned_end_end)
    if q.updated_after:
        conditions.append(ProductionTaskOrder.updated_at >= q.updated_after)

    total = (await db.execute(select(func.count(ProductionTaskOrder.id)).where(*conditions))).scalar() or 0
    rows = (
        await db.execute(
            _task_orders_with_order_no()
            .where(*conditions)
            .order_by(ProductionTaskOrder.updated_at.desc(), ProductionTaskOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return {
        "items": [_serialize_task_order(row, order_no) for row, order_no in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        **await _freshness(db, ProductionTaskOrder.updated_at, sync_types=("production_task_orders",)),
        "request_id": q.request_id,
    }


# ---------------------------------------------------------------- operations

_OPERATION_STATUS_MAP = {"pending": "planned", "in_progress": "in_progress", "completed": "completed", "done": "completed"}


def _map_operation_status(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    return _OPERATION_STATUS_MAP.get(raw.lower(), "unknown")


def _serialize_progress(row: ProcessProgress) -> dict:
    return {
        "operation_id": str(row.id),
        "work_order_id": None,
        "work_order_no": None,
        "order_no": row.order_no,
        "line_no": row.line_no,
        "operation_seq": row.seq_no,
        "operation_code": row.process_type,
        "operation_name": row.process_type,
        "route_version": None,
        "predecessor_operation_ids": None,
        "work_center_code": None,
        "product_code": row.product_code,
        "product_name": row.product_name,
        "model_code": row.model_code,
        "planned_qty": _n(row.planned_qty),
        "qty": _n(row.qty),
        "kit_qty": _n(row.kit_qty),
        "daily_plan_qty": _n(row.daily_plan_qty),
        "daily_complete_qty": _n(row.daily_complete_qty),
        "good_qty": None,
        "scrap_qty": None,
        "uom": None,
        "completion_rate": row.completion_rate,
        "work_hours": _n(row.work_hours),
        "planned_start_at": _d(row.plan_date),
        "planned_end_at": None,
        "actual_start_at": _d(row.online_date),
        "actual_end_at": None,
        "status_raw": row.status,
        "status": _map_operation_status(row.status),
        "blocking_reason": None,
        "next_process": row.next_process,
        "last_reported_at": None,
        "data_source": row.data_source,
        "updated_at": _d(row.updated_at),
    }


class OperationOut(BaseModel):
    operation_id: str
    work_order_id: Optional[str] = None
    work_order_no: Optional[str] = None
    order_no: Optional[str] = None
    line_no: Optional[str] = None
    operation_seq: Optional[int] = None
    operation_code: Optional[str] = None
    operation_name: Optional[str] = None
    route_version: Optional[str] = None
    predecessor_operation_ids: Optional[str] = None
    work_center_code: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    model_code: Optional[str] = None
    planned_qty: Optional[float] = None
    qty: Optional[float] = None
    kit_qty: Optional[float] = None
    daily_plan_qty: Optional[float] = None
    daily_complete_qty: Optional[float] = None
    good_qty: Optional[float] = None
    scrap_qty: Optional[float] = None
    uom: Optional[str] = None
    completion_rate: Optional[str] = None
    work_hours: Optional[float] = None
    planned_start_at: Optional[str] = None
    planned_end_at: Optional[str] = None
    actual_start_at: Optional[str] = None
    actual_end_at: Optional[str] = None
    status_raw: Optional[str] = None
    status: str = "unknown"
    blocking_reason: Optional[str] = None
    next_process: Optional[str] = None
    last_reported_at: Optional[str] = None
    data_source: Optional[str] = None
    updated_at: Optional[str] = None


class OperationsListQuery(PageParamsMixin):
    order_no: Optional[str] = Field(None, description="订单号精确匹配（必填锚点：SPC 工序进度无工单外键）")
    process_type: Optional[str] = Field(None, description="工序类型逗号分隔多选：前道/贴片/精益/组装/包装")
    status: Optional[str] = Field(None, description="原始状态逗号分隔多选，如 pending,in_progress")
    plan_date_start: Optional[date] = Field(None, description="计划日期起 YYYY-MM-DD（含）")
    plan_date_end: Optional[date] = Field(None, description="计划日期止 YYYY-MM-DD（含）")
    updated_after: Optional[datetime] = Field(None, description="增量同步，仅返回 updated_at >= 此时间的记录（ISO 8601）")
    request_id: Optional[str] = Field(None, description="调用方请求 ID（回显）")


@router.get("/operations/list", response_model=ResponseModel[ExternalDataPage[OperationOut]],
            summary="工序进度列表", description="endpoint_code: production.operations.list")
@register_external(
    "production.operations.list", "工序进度列表", method="GET", path="/production/operations/list",
    description="工序进度统一模型（前道/贴片/精益/组装/包装）；order_no 必填；工单/工作中心/前置工序无来源恒 null",
    tags=["生产协同"],
)
@log_external_call("production.operations.list")
async def production_operations_list(
    request: Request,
    q: Annotated[OperationsListQuery, Query()],
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("production.operations.list")),
):
    if not q.order_no:
        raise HTTPException(status_code=422, detail="order_no 必填（SPC 工序进度以订单号为锚点，无工单外键）")
    page, page_size = _page(q)
    conditions = [ProcessProgress.order_no == q.order_no]
    if q.process_type:
        types = [s.strip() for s in q.process_type.split(",") if s.strip()]
        if types:
            conditions.append(ProcessProgress.process_type.in_(types))
    if q.status:
        statuses = [s.strip() for s in q.status.split(",") if s.strip()]
        if statuses:
            conditions.append(ProcessProgress.status.in_(statuses))
    if q.plan_date_start:
        conditions.append(ProcessProgress.plan_date >= q.plan_date_start)
    if q.plan_date_end:
        conditions.append(ProcessProgress.plan_date <= q.plan_date_end)
    if q.updated_after:
        conditions.append(ProcessProgress.updated_at >= q.updated_after)

    total = (await db.execute(select(func.count(ProcessProgress.id)).where(*conditions))).scalar() or 0
    rows = (
        await db.execute(
            select(ProcessProgress)
            .where(*conditions)
            .order_by(ProcessProgress.plan_date.desc().nullslast(), ProcessProgress.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "items": [_serialize_progress(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        **await _freshness(db, ProcessProgress.updated_at,
                           sync_types=("production_task_orders",),
                           import_tables=("process_progress",), baseline=True),
        "request_id": q.request_id,
    }


# ---------------------------------------------------------------- order-links

def _serialize_task_link(row: ProductionTaskOrder, order_no: Optional[str] = None) -> dict:
    return {
        "link_id": f"production_task:{row.id}",
        "link_type": "production_task",
        "work_order_id": str(row.id),
        "work_order_no": row.task_no,
        "order_no": order_no or row.sale_order_no,
        "line_no": None,
        "order_line_id": None,
        "allocated_qty": _n(row.task_qty),
        "uom": None,
        "allocation_version": None,
        "schedule_plan_id": None,
        "product_code": row.material_code,
        "scheduling_status": None,
        "promised_date": _d(row.planned_end_date),
        "updated_at": _d(row.updated_at),
    }


def _serialize_snapshot_link(row: ProductionOrderScheduleSnapshot) -> dict:
    return {
        "link_id": f"schedule_snapshot:{row.id}",
        "link_type": "schedule_snapshot",
        "work_order_id": None,
        "work_order_no": None,
        "order_no": row.order_no,
        "line_no": row.line_no,
        "order_line_id": str(row.sale_order_line_id) if row.sale_order_line_id is not None else None,
        "allocated_qty": None,
        "uom": None,
        "allocation_version": None,
        "schedule_plan_id": None,
        "product_code": row.product_code,
        "scheduling_status": row.scheduling_status,
        "promised_date": _d(row.promised_date),
        "updated_at": _d(row.updated_at),
    }


class OrderLinkOut(BaseModel):
    link_id: str
    link_type: str
    work_order_id: Optional[str] = None
    work_order_no: Optional[str] = None
    order_no: Optional[str] = None
    line_no: Optional[str] = None
    order_line_id: Optional[str] = None
    allocated_qty: Optional[float] = None
    uom: Optional[str] = None
    allocation_version: Optional[str] = None
    schedule_plan_id: Optional[int] = None
    product_code: Optional[str] = None
    scheduling_status: Optional[str] = None
    promised_date: Optional[str] = None
    updated_at: Optional[str] = None


class OrderLinksListQuery(PageParamsMixin):
    work_order_no: Optional[str] = Field(None, description="任务单号精确匹配（与 order_no 至少一个）")
    order_no: Optional[str] = Field(None, description="销售订单号精确匹配（与 work_order_no 至少一个）")
    link_type: Optional[str] = Field(None, description="关联来源逗号分隔多选：production_task,schedule_snapshot")
    updated_after: Optional[datetime] = Field(None, description="增量同步，仅返回 updated_at >= 此时间的记录（ISO 8601）")
    request_id: Optional[str] = Field(None, description="调用方请求 ID（回显）")


@router.get("/order-links/list", response_model=ResponseModel[ExternalDataPage[OrderLinkOut]],
            summary="工单与销售订单关系", description="endpoint_code: production.order_links.list")
@register_external(
    "production.order_links.list", "工单与销售订单关系", method="GET", path="/production/order-links/list",
    description="双源：production_task（任务单→订单，订单级，line_no 恒 null；订单号经 sale_order.erp_id 解析）+ schedule_snapshot（订单行级排产快照，无工单号）；不做产品编码推断",
    tags=["生产协同"],
)
@log_external_call("production.order_links.list")
async def production_order_links_list(
    request: Request,
    q: Annotated[OrderLinksListQuery, Query()],
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("production.order_links.list")),
):
    if not (q.work_order_no or q.order_no):
        raise HTTPException(status_code=422, detail="work_order_no / order_no 至少提供一个")
    page, page_size = _page(q)
    link_types = {s.strip() for s in (q.link_type or "").split(",") if s.strip()} or {"production_task", "schedule_snapshot"}

    links: list[dict] = []
    if "production_task" in link_types:
        conditions = []
        if q.work_order_no:
            conditions.append(ProductionTaskOrder.task_no == q.work_order_no)
        if q.order_no:
            conditions.append(_order_no_filter(q.order_no))
        tasks = (await db.execute(
            _task_orders_with_order_no().where(*conditions).order_by(ProductionTaskOrder.id)
        )).all()
        links.extend(_serialize_task_link(row, order_no) for row, order_no in tasks)

    if "schedule_snapshot" in link_types and q.order_no:
        snapshots = (await db.execute(
            select(ProductionOrderScheduleSnapshot)
            .where(ProductionOrderScheduleSnapshot.order_no == q.order_no)
            .order_by(ProductionOrderScheduleSnapshot.line_no)
        )).scalars().all()
        links.extend(_serialize_snapshot_link(s) for s in snapshots)

    if q.updated_after:
        links = [
            ln for ln in links
            if (dt := _parse_iso(ln["updated_at"])) is not None and dt >= q.updated_after
        ]

    links.sort(key=lambda ln: (_parse_iso(ln["updated_at"]) or datetime.min, ln["link_id"]), reverse=True)
    total = len(links)
    start = (page - 1) * page_size
    return {
        "items": links[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        **await _freshness(
            db, ProductionTaskOrder.updated_at, ProductionOrderScheduleSnapshot.updated_at,
            sync_types=("production_task_orders",)),
        "request_id": q.request_id,
    }


# ---------------------------------------------------------------- reports

def _serialize_daily_report(row: ProductionDailyReport) -> dict:
    return {
        "report_id": str(row.id),
        "report_uid": row.oa_id,
        "report_line_id": str(row.oa_detail_id) if row.oa_detail_id is not None else None,
        "report_type": "daily_erp",
        "work_order_id": None,
        "work_order_no": row.production_order_no,
        "operation_id": None,
        "operation_name": row.process,
        "order_no": row.sale_order_no,
        "material_code": row.material_code,
        "bom_no": row.bom_no,
        "specification": row.specification,
        "reported_qty": _n(row.completed_qty),
        "good_qty": None,
        "scrap_qty": None,
        "uom": None,
        "reported_at": _d(row.report_date),
        "reported_by": None,
        "workshop": row.workshop,
        "work_hours": _n(row.work_hours),
        "is_reversed": None,
        "reversal_of": None,
        "revision": None,
        "erp_updated_at": _d(row.erp_updated_at),
        "updated_at": _d(row.updated_at),
    }


class ReportOut(BaseModel):
    report_id: str
    report_uid: Optional[str] = None
    report_line_id: Optional[str] = None
    report_type: Optional[str] = None
    work_order_id: Optional[str] = None
    work_order_no: Optional[str] = None
    operation_id: Optional[str] = None
    operation_name: Optional[str] = None
    order_no: Optional[str] = None
    material_code: Optional[str] = None
    bom_no: Optional[str] = None
    specification: Optional[str] = None
    reported_qty: Optional[float] = None
    good_qty: Optional[float] = None
    scrap_qty: Optional[float] = None
    uom: Optional[str] = None
    reported_at: Optional[str] = None
    reported_by: Optional[str] = None
    workshop: Optional[str] = None
    work_hours: Optional[float] = None
    is_reversed: Optional[bool] = None
    reversal_of: Optional[str] = None
    revision: Optional[str] = None
    erp_updated_at: Optional[str] = None
    updated_at: Optional[str] = None


class ReportsListQuery(PageParamsMixin):
    work_order_no: Optional[str] = Field(None, description="生产订单号精确匹配（必填锚点）")
    order_no: Optional[str] = Field(None, description="销售订单号精确匹配")
    report_date_start: Optional[date] = Field(None, description="报工日期起 YYYY-MM-DD（含）")
    report_date_end: Optional[date] = Field(None, description="报工日期止 YYYY-MM-DD（含）")
    updated_after: Optional[datetime] = Field(None, description="增量同步，仅返回 updated_at >= 此时间的记录（ISO 8601）")
    request_id: Optional[str] = Field(None, description="调用方请求 ID（回显）")


@router.get("/reports/list", response_model=ResponseModel[ExternalDataPage[ReportOut]],
            summary="生产报工列表", description="endpoint_code: production.reports.list")
@register_external(
    "production.reports.list", "生产报工列表", method="GET", path="/production/reports/list",
    description="ERP 生产日报（累计口径）；work_order_no 必填；撤销/更正无来源恒 null（is_reversed/reversal_of/revision）",
    tags=["生产协同"],
)
@log_external_call("production.reports.list")
async def production_reports_list(
    request: Request,
    q: Annotated[ReportsListQuery, Query()],
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("production.reports.list")),
):
    if not q.work_order_no:
        raise HTTPException(status_code=422, detail="work_order_no 必填（按生产订单号查询 ERP 生产日报）")
    page, page_size = _page(q)
    conditions = [ProductionDailyReport.production_order_no == q.work_order_no]
    if q.order_no:
        conditions.append(ProductionDailyReport.sale_order_no == q.order_no)
    if q.report_date_start:
        conditions.append(ProductionDailyReport.report_date >= q.report_date_start)
    if q.report_date_end:
        conditions.append(ProductionDailyReport.report_date <= q.report_date_end)
    if q.updated_after:
        conditions.append(ProductionDailyReport.updated_at >= q.updated_after)

    total = (await db.execute(select(func.count(ProductionDailyReport.id)).where(*conditions))).scalar() or 0
    rows = (
        await db.execute(
            select(ProductionDailyReport)
            .where(*conditions)
            .order_by(ProductionDailyReport.report_date.desc().nullslast(), ProductionDailyReport.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "items": [_serialize_daily_report(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        **await _freshness(db, ProductionDailyReport.updated_at,
                           sync_types=("production_daily_reports",), baseline=True),
        "request_id": q.request_id,
    }


# ---------------------------------------------------------------- capacity

def _available_minutes(base: Optional[ProductionBaseCondition], day: date) -> Optional[float]:
    if base is None:
        return None
    if day.weekday() == 6 and not base.include_sunday:
        return 0.0
    return _n(base.daily_work_hours) * 60 if base.daily_work_hours is not None else None


class CapacityOut(BaseModel):
    work_center_code: str
    department: Optional[str] = None
    schedule_bucket: Optional[str] = None
    bucket_label: Optional[str] = None
    capacity_date: Optional[str] = None
    shift_id: Optional[str] = None
    calendar_version: Optional[str] = None
    schedule_version: Optional[str] = None
    available_minutes: Optional[float] = None
    planned_load_minutes: Optional[float] = None
    downtime_minutes: Optional[float] = None
    occupied_slot_count: Optional[int] = None
    updated_at: Optional[str] = None


class CapacityListQuery(PageParamsMixin):
    department: Optional[str] = Field(None, description="车间/部门精确匹配（缺省为全部）")
    schedule_bucket: Optional[str] = Field(None, description="排产段精确匹配：lean/assembly/packaging")
    date_start: Optional[date] = Field(None, description="日期起 YYYY-MM-DD（必填，含）")
    date_end: Optional[date] = Field(None, description="日期止 YYYY-MM-DD（必填，含）")
    updated_after: Optional[datetime] = Field(None, description="增量同步，仅返回 updated_at >= 此时间的占用槽（ISO 8601）")
    request_id: Optional[str] = Field(None, description="调用方请求 ID（回显）")


@router.get("/capacity/list", response_model=ResponseModel[ExternalDataPage[CapacityOut]],
            summary="产能占用与可用分钟", description="endpoint_code: production.capacity.list")
@register_external(
    "production.capacity.list", "产能占用与可用分钟", method="GET", path="/production/capacity/list",
    description="按（部门, 排产段, 日期）聚合时间槽占用；可用分钟来自排产基础条件（周日不排产为 0，缺基础条件为 null）；shift/downtime 无来源恒 null",
    tags=["生产协同"],
)
@log_external_call("production.capacity.list")
async def production_capacity_list(
    request: Request,
    q: Annotated[CapacityListQuery, Query()],
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("production.capacity.list")),
):
    if not q.date_start or not q.date_end:
        raise HTTPException(status_code=422, detail="date_start / date_end 必填（产能按日期窗口聚合）")
    if q.date_start > q.date_end:
        raise HTTPException(status_code=422, detail="date_start 不能晚于 date_end")
    page, page_size = _page(q)

    conditions = [
        CapacitySlot.is_active == True,  # noqa: E712 — SQLAlchemy 比较 bundled bool 需显式 True
        func.date(CapacitySlot.slot_date) >= q.date_start,
        func.date(CapacitySlot.slot_date) <= q.date_end,
    ]
    if q.department:
        conditions.append(CapacitySlot.department == q.department)
    if q.schedule_bucket:
        conditions.append(CapacitySlot.schedule_bucket == q.schedule_bucket)
    if q.updated_after:
        conditions.append(CapacitySlot.updated_at >= q.updated_after)

    slot_day = func.date(CapacitySlot.slot_date).label("slot_day")
    groups = (
        await db.execute(
            select(
                CapacitySlot.department,
                CapacitySlot.schedule_bucket,
                slot_day,
                func.sum(CapacitySlot.hours).label("total_hours"),
                func.count(CapacitySlot.id).label("slot_count"),
                func.max(CapacitySlot.updated_at).label("max_updated_at"),
            )
            .where(*conditions)
            .group_by(CapacitySlot.department, CapacitySlot.schedule_bucket, slot_day)
            .order_by(slot_day.desc(), CapacitySlot.department, CapacitySlot.schedule_bucket)
        )
    ).all()

    bases = {
        b.schedule_bucket: b
        for b in (await db.execute(
            select(ProductionBaseCondition).where(ProductionBaseCondition.is_active == True)  # noqa: E712
        )).scalars().all()
    }

    items = []
    for department, bucket, day, total_hours, slot_count, max_updated_at in groups:
        base = bases.get(bucket)
        items.append({
            "work_center_code": f"{department}:{bucket}",
            "department": department,
            "schedule_bucket": bucket,
            "bucket_label": base.bucket_label if base else None,
            "capacity_date": _d(day),
            "shift_id": None,
            "calendar_version": None,
            "schedule_version": None,
            "available_minutes": _available_minutes(base, day),
            "planned_load_minutes": _n(total_hours) * 60 if total_hours is not None else None,
            "downtime_minutes": None,
            "occupied_slot_count": slot_count,
            "updated_at": _d(max_updated_at),
        })

    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        **await _freshness(db, CapacitySlot.updated_at, baseline=True),
        "request_id": q.request_id,
    }
