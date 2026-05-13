from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, asc, desc, case
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from sqlalchemy.orm import selectinload
from datetime import date

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.audit import log_audit
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.material.material_demand import MaterialDemand
from app.models.material.binding import OrderMaterialPoBinding
from app.schemas.common import ResponseModel, PageResult
from app.models.exception.risk_issue import RiskIssue
from app.schemas.order.schemas import SaleOrderOut, SaleOrderUpdate, OrderCreate, OrderDetailOut, MaterialDemandOut, BindingOut, PODetail, RiskIssueOut, SaleOrderListOut, SaleOrderLineOut

router = APIRouter()

SORTABLE_COLUMNS = {
    'department': SaleOrder.department,
    'delivery_completed_date': SaleOrder.delivery_completed_date,
    'customer_grade': SaleOrder.customer_grade,
    'customer_code': SaleOrder.customer_code,
    'order_no': SaleOrder.order_no,
    'order_qty': SaleOrder.order_qty,
    'order_date': SaleOrder.order_date,
    'promised_date': SaleOrder.promised_date,
    'shipping_plan': SaleOrder.shipping_plan,
    'customer_inspection_date': SaleOrder.customer_inspection_date,
    'planned_start_date': SaleOrder.planned_start_date,
    'bom_return_date': SaleOrder.bom_return_date,
    'material_ready_date': SaleOrder.material_ready_date,
    'front_process_date': SaleOrder.front_process_date,
    'first_article_date': SaleOrder.first_article_date,
    'assembly_start_date': SaleOrder.assembly_start_date,
    'assembly_complete_date': SaleOrder.assembly_complete_date,
    'risk_score': SaleOrder.risk_score,
}


@router.get("", response_model=ResponseModel[PageResult[SaleOrderListOut]])
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: Optional[str] = Query(None, description="风险等级，多选逗号分隔如 red,yellow"),
    keyword: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    customer: Optional[str] = Query(None),
    customer_grade: Optional[str] = Query(None, description="客户等级，多选逗号分隔如 A,B"),
    data_source: Optional[str] = Query(None),
    department: Optional[str] = Query(None, description="销售部门，多选逗号分隔"),
    status: Optional[str] = Query(None, description="订单状态，多选逗号分隔"),
    inspection_result: Optional[str] = Query(None, description="客检结果，多选逗号分隔"),
    packaging_status: Optional[str] = Query(None, description="包装状态，多选逗号分隔"),
    procurement_status: Optional[str] = Query(None, description="采购状态，多选逗号分隔"),
    delivery_completed: Optional[str] = Query(None, description="发货完成状态: yes/no"),
    promised_date_start: Optional[str] = Query(None, description="合同交期开始日期 YYYY-MM-DD"),
    promised_date_end: Optional[str] = Query(None, description="合同交期结束日期 YYYY-MM-DD"),
    shipping_plan_start: Optional[str] = Query(None, description="出货计划开始日期 YYYY-MM-DD"),
    shipping_plan_end: Optional[str] = Query(None, description="出货计划结束日期 YYYY-MM-DD"),
    order_date_start: Optional[str] = Query(None, description="下单时间开始日期 YYYY-MM-DD"),
    order_date_end: Optional[str] = Query(None, description="下单时间结束日期 YYYY-MM-DD"),
    sort_by: Optional[str] = Query("promised_date", description="排序字段"),
    sort_order: Optional[str] = Query("asc", description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("orders.list", "read")),
    db: AsyncSession = Depends(get_db),
):
    query = select(SaleOrder)
    count_query = select(func.count(SaleOrder.id))

    if risk_level:
        levels = [x.strip() for x in risk_level.split(',') if x.strip()]
        if len(levels) == 1:
            query = query.where(SaleOrder.risk_level == levels[0])
            count_query = count_query.where(SaleOrder.risk_level == levels[0])
        elif levels:
            query = query.where(SaleOrder.risk_level.in_(levels))
            count_query = count_query.where(SaleOrder.risk_level.in_(levels))
    if owner:
        query = query.where(SaleOrder.owner == owner)
        count_query = count_query.where(SaleOrder.owner == owner)
    if customer:
        like_expr = f"%{customer}%"
        query = query.where(SaleOrder.customer.ilike(like_expr))
        count_query = count_query.where(SaleOrder.customer.ilike(like_expr))
    if customer_grade:
        grades = [x.strip() for x in customer_grade.split(',') if x.strip()]
        if len(grades) == 1:
            query = query.where(SaleOrder.customer_grade == grades[0])
            count_query = count_query.where(SaleOrder.customer_grade == grades[0])
        elif grades:
            query = query.where(SaleOrder.customer_grade.in_(grades))
            count_query = count_query.where(SaleOrder.customer_grade.in_(grades))
    if data_source:
        query = query.where(SaleOrder.data_source == data_source)
        count_query = count_query.where(SaleOrder.data_source == data_source)
    if department:
        departments = [x.strip() for x in department.split(',') if x.strip()]
        if len(departments) == 1:
            query = query.where(SaleOrder.department == departments[0])
            count_query = count_query.where(SaleOrder.department == departments[0])
        elif departments:
            query = query.where(SaleOrder.department.in_(departments))
            count_query = count_query.where(SaleOrder.department.in_(departments))
    if status:
        statuses = [x.strip() for x in status.split(',') if x.strip()]
        if len(statuses) == 1:
            query = query.where(SaleOrder.status == statuses[0])
            count_query = count_query.where(SaleOrder.status == statuses[0])
        elif statuses:
            query = query.where(SaleOrder.status.in_(statuses))
            count_query = count_query.where(SaleOrder.status.in_(statuses))
    if inspection_result:
        results = [x.strip() for x in inspection_result.split(',') if x.strip()]
        if len(results) == 1:
            query = query.where(SaleOrder.inspection_result == results[0])
            count_query = count_query.where(SaleOrder.inspection_result == results[0])
        elif results:
            query = query.where(SaleOrder.inspection_result.in_(results))
            count_query = count_query.where(SaleOrder.inspection_result.in_(results))
    if packaging_status:
        statuses = [x.strip() for x in packaging_status.split(',') if x.strip()]
        if len(statuses) == 1:
            query = query.where(SaleOrder.packaging_status == statuses[0])
            count_query = count_query.where(SaleOrder.packaging_status == statuses[0])
        elif statuses:
            query = query.where(SaleOrder.packaging_status.in_(statuses))
            count_query = count_query.where(SaleOrder.packaging_status.in_(statuses))
    if procurement_status:
        statuses = [x.strip() for x in procurement_status.split(',') if x.strip()]
        if len(statuses) == 1:
            query = query.where(SaleOrder.procurement_status == statuses[0])
            count_query = count_query.where(SaleOrder.procurement_status == statuses[0])
        elif statuses:
            query = query.where(SaleOrder.procurement_status.in_(statuses))
            count_query = count_query.where(SaleOrder.procurement_status.in_(statuses))
    if delivery_completed:
        if delivery_completed == 'yes':
            query = query.where(SaleOrder.delivery_completed_date.isnot(None))
            count_query = count_query.where(SaleOrder.delivery_completed_date.isnot(None))
        elif delivery_completed == 'no':
            query = query.where(SaleOrder.delivery_completed_date.is_(None))
            count_query = count_query.where(SaleOrder.delivery_completed_date.is_(None))
    if promised_date_start:
        query = query.where(SaleOrder.promised_date >= promised_date_start)
        count_query = count_query.where(SaleOrder.promised_date >= promised_date_start)
    if promised_date_end:
        query = query.where(SaleOrder.promised_date <= promised_date_end)
        count_query = count_query.where(SaleOrder.promised_date <= promised_date_end)
    if shipping_plan_start:
        query = query.where(SaleOrder.shipping_plan >= shipping_plan_start)
        count_query = count_query.where(SaleOrder.shipping_plan >= shipping_plan_start)
    if shipping_plan_end:
        query = query.where(SaleOrder.shipping_plan <= shipping_plan_end)
        count_query = count_query.where(SaleOrder.shipping_plan <= shipping_plan_end)
    if order_date_start:
        query = query.where(SaleOrder.order_date >= order_date_start)
        count_query = count_query.where(SaleOrder.order_date >= order_date_start)
    if order_date_end:
        query = query.where(SaleOrder.order_date <= order_date_end)
        count_query = count_query.where(SaleOrder.order_date <= order_date_end)
    if keyword:
        like_expr = f"%{keyword}%"
        query = query.where(
            (SaleOrder.order_no.ilike(like_expr)) | (SaleOrder.customer.ilike(like_expr)) | (SaleOrder.product_name.ilike(like_expr))
        )
        count_query = count_query.where(
            (SaleOrder.order_no.ilike(like_expr)) | (SaleOrder.customer.ilike(like_expr)) | (SaleOrder.product_name.ilike(like_expr))
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 全局风险等级统计（用于统计卡片）
    global_stats_query = select(
        func.count(SaleOrder.id).label('total'),
        func.sum(case((SaleOrder.risk_level == 'red', 1), else_=0)).label('red_count'),
        func.sum(case((SaleOrder.risk_level == 'yellow', 1), else_=0)).label('yellow_count'),
        func.sum(case((SaleOrder.risk_level == 'blue', 1), else_=0)).label('blue_count'),
        func.sum(case((SaleOrder.risk_level == 'green', 1), else_=0)).label('green_count'),
    )
    # 全局统计不受 keyword/risk_level/status 等筛选影响
    global_stats_result = await db.execute(global_stats_query)
    global_stats = global_stats_result.first()

    # 欠料统计
    shortage_stats_result = await db.execute(
        select(func.count(MaterialDemand.id.distinct()).label('shortage_count'))
        .where(MaterialDemand.shortage_flag == True)
    )
    shortage_stats = shortage_stats_result.first()

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
        order_clauses = [SaleOrder.promised_date.asc().nullslast(), SaleOrder.id.desc()]

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Sorting: sort_by={sort_by}, sort_order={sort_order}, order_clauses={order_clauses}")

    query = query.options(selectinload(SaleOrder.lines)).order_by(*order_clauses).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.scalars().all()

    order_nos = [order.order_no for order in orders]
    shortage_map: dict[str, int] = {}
    if order_nos:
        shortage_result = await db.execute(
            select(
                MaterialDemand.order_no,
                func.count(MaterialDemand.id).label("cnt"),
            )
            .where(
                MaterialDemand.order_no.in_(order_nos),
                MaterialDemand.shortage_flag == True,
            )
            .group_by(MaterialDemand.order_no)
        )
        shortage_map = {row.order_no: row.cnt for row in shortage_result.all()}

    items = []
    for order in orders:
        promised_dates = [line.promised_date for line in order.lines if line.promised_date]
        planned_dates = [line.planned_start_date for line in order.lines if line.planned_start_date]
        order_dict = SaleOrderOut.model_validate(order).model_dump()
        order_dict.update(
            product_count=len({line.product_code for line in order.lines if line.product_code}),
            line_count=len(order.lines),
            shortage_count=shortage_map.get(order.order_no, 0),
            promised_date=order.promised_date or (min(promised_dates) if promised_dates else None),
            planned_start_date=order.planned_start_date or (min(planned_dates) if planned_dates else None),
        )
        items.append(SaleOrderListOut(**order_dict))

    page_result = PageResult(total=total, page=page, page_size=page_size, items=items)
    # 将全局统计添加到返回数据中
    page_result.stats = {
        'total': global_stats.total or 0,
        'red_count': global_stats.red_count or 0,
        'yellow_count': global_stats.yellow_count or 0,
        'blue_count': global_stats.blue_count or 0,
        'green_count': global_stats.green_count or 0,
        'shortage_count': shortage_stats.shortage_count or 0,
    }

    return ResponseModel(data=page_result)


# ── 内销订单 ──
@router.get("/domestic", response_model=ResponseModel[PageResult[SaleOrderListOut]])
async def list_domestic_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("promised_date", description="排序字段"),
    sort_order: Optional[str] = Query("asc", description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("orders.list", "read")),
    db: AsyncSession = Depends(get_db),
):
    """内销订单 — 过滤department='内销部'"""
    base_filter = SaleOrder.department == '内销部'
    query = select(SaleOrder).where(base_filter)
    count_query = select(func.count(SaleOrder.id)).where(base_filter)

    if status:
        query = query.where(SaleOrder.status == status)
        count_query = count_query.where(SaleOrder.status == status)
    if keyword:
        like_expr = f"%{keyword}%"
        kw_filter = (SaleOrder.order_no.ilike(like_expr)) | (SaleOrder.customer.ilike(like_expr))
        query = query.where(kw_filter)
        count_query = count_query.where(kw_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 构建排序子句
    order_clauses = []
    if sort_by and sort_by in SORTABLE_COLUMNS:
        col = SORTABLE_COLUMNS[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    if not order_clauses:
        order_clauses = [SaleOrder.promised_date.asc().nullslast(), SaleOrder.id.desc()]

    query = query.options(selectinload(SaleOrder.lines)).order_by(*order_clauses).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.scalars().all()

    items = []
    for order in orders:
        order_dict = SaleOrderOut.model_validate(order).model_dump()
        order_dict.update(product_count=0, line_count=len(order.lines), shortage_count=0)
        items.append(SaleOrderListOut(**order_dict))

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


# ── 内销出货 ──
@router.get("/domestic-shipment", response_model=ResponseModel[PageResult[SaleOrderListOut]])
async def list_domestic_shipment(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    shipped: Optional[bool] = Query(None),
    sort_by: Optional[str] = Query("shipping_plan", description="排序字段"),
    sort_order: Optional[str] = Query("desc", description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("orders.list", "read")),
    db: AsyncSession = Depends(get_db),
):
    """内销出货 — 内销部订单的发货视图"""
    base_filter = SaleOrder.department == '内销部'
    query = select(SaleOrder).where(base_filter)
    count_query = select(func.count(SaleOrder.id)).where(base_filter)

    if shipped is True:
        query = query.where(SaleOrder.delivery_completed_date.isnot(None))
        count_query = count_query.where(SaleOrder.delivery_completed_date.isnot(None))
    elif shipped is False:
        query = query.where(SaleOrder.delivery_completed_date.is_(None))
        count_query = count_query.where(SaleOrder.delivery_completed_date.is_(None))
    if keyword:
        like_expr = f"%{keyword}%"
        kw_filter = (SaleOrder.order_no.ilike(like_expr)) | (SaleOrder.customer.ilike(like_expr))
        query = query.where(kw_filter)
        count_query = count_query.where(kw_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 全局统计（用于统计卡片）
    global_stats_query = select(
        func.count(SaleOrder.id).label('total'),
        func.sum(case((SaleOrder.delivery_completed_date.isnot(None), 1), else_=0)).label('shipped_count'),
    ).where(base_filter)
    # 全局统计不受 keyword/shipped 筛选影响
    global_stats_result = await db.execute(global_stats_query)
    global_stats = global_stats_result.first()

    # 构建排序子句
    order_clauses = []
    if sort_by and sort_by in SORTABLE_COLUMNS:
        col = SORTABLE_COLUMNS[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    if not order_clauses:
        order_clauses = [SaleOrder.shipping_plan.desc().nullslast(), SaleOrder.id.desc()]

    query = query.options(selectinload(SaleOrder.lines)).order_by(*order_clauses).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.scalars().all()

    items = []
    for order in orders:
        order_dict = SaleOrderOut.model_validate(order).model_dump()
        order_dict.update(product_count=0, line_count=len(order.lines), shortage_count=0)
        items.append(SaleOrderListOut(**order_dict))

    page_result = PageResult(total=total, page=page, page_size=page_size, items=items)
    # 将全局统计添加到返回数据中
    page_result.stats = {
        'total': global_stats.total or 0,
        'shipped_count': global_stats.shipped_count or 0,
        'pending_count': (global_stats.total or 0) - (global_stats.shipped_count or 0),
    }

    return ResponseModel(data=page_result)


# ── 订单风险池 ──
@router.get("/risk-pool", response_model=ResponseModel[PageResult[SaleOrderListOut]])
async def list_risk_pool(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None, description="风险等级，多选逗号分隔如 red,yellow"),
    sort_by: Optional[str] = Query("promised_date", description="排序字段"),
    sort_order: Optional[str] = Query("asc", description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("orders.risk_pool", "read")),
    db: AsyncSession = Depends(get_db),
):
    """订单风险池 — 延期 + 高/中风险订单"""
    from sqlalchemy import or_
    today = date.today()
    risk_filter = or_(
        SaleOrder.risk_level.in_(['red', 'yellow']),
        (SaleOrder.promised_date < today) & (SaleOrder.status != 'closed'),
    )
    query = select(SaleOrder).where(risk_filter)
    count_query = select(func.count(SaleOrder.id)).where(risk_filter)

    if risk_level:
        levels = [x.strip() for x in risk_level.split(',') if x.strip()]
        if len(levels) == 1:
            query = query.where(SaleOrder.risk_level == levels[0])
            count_query = count_query.where(SaleOrder.risk_level == levels[0])
        elif levels:
            query = query.where(SaleOrder.risk_level.in_(levels))
            count_query = count_query.where(SaleOrder.risk_level.in_(levels))
    if keyword:
        like_expr = f"%{keyword}%"
        kw_filter = (SaleOrder.order_no.ilike(like_expr)) | (SaleOrder.customer.ilike(like_expr))
        query = query.where(kw_filter)
        count_query = count_query.where(kw_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 全局风险等级统计（用于统计卡片）
    global_stats_query = select(
        func.count(SaleOrder.id).label('total'),
        func.sum(case((SaleOrder.risk_level == 'red', 1), else_=0)).label('red_count'),
        func.sum(case((SaleOrder.risk_level == 'yellow', 1), else_=0)).label('yellow_count'),
        func.sum(case((SaleOrder.risk_level == 'blue', 1), else_=0)).label('blue_count'),
        func.sum(case((SaleOrder.risk_level == 'green', 1), else_=0)).label('green_count'),
        func.sum(case(((SaleOrder.promised_date < today) & (SaleOrder.status != 'closed'), 1), else_=0)).label('overdue_count'),
    ).where(risk_filter)

    # 全局统计不受 keyword 和 risk_level 筛选影响
    global_stats_result = await db.execute(global_stats_query)
    global_stats = global_stats_result.first()

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
        order_clauses = [SaleOrder.promised_date.asc().nullslast(), SaleOrder.id.desc()]

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Sorting: sort_by={sort_by}, sort_order={sort_order}, order_clauses={order_clauses}")

    query = query.options(selectinload(SaleOrder.lines)).order_by(*order_clauses).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.scalars().all()

    items = []
    for order in orders:
        order_dict = SaleOrderOut.model_validate(order).model_dump()
        order_dict.update(product_count=0, line_count=len(order.lines), shortage_count=0)
        items.append(SaleOrderListOut(**order_dict))

    page_result = PageResult(total=total, page=page, page_size=page_size, items=items)
    # 将全局统计添加到返回数据中
    page_result.stats = {
        'total': global_stats.total or 0,
        'red_count': global_stats.red_count or 0,
        'yellow_count': global_stats.yellow_count or 0,
        'blue_count': global_stats.blue_count or 0,
        'green_count': global_stats.green_count or 0,
        'overdue_count': global_stats.overdue_count or 0,
    }

    return ResponseModel(data=page_result)


@router.get("/{order_no}", response_model=ResponseModel[OrderDetailOut])
@router.get("/{order_no}/lines/{line_no}", response_model=ResponseModel[OrderDetailOut])
async def get_order_detail(
    order_no: str,
    line_no: Optional[str] = None,
    current_user: dict = Depends(PermissionChecker("orders.list", "read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(SaleOrder).options(selectinload(SaleOrder.lines)).where(SaleOrder.order_no == order_no)
    if line_no:
        q = q.where(SaleOrder.line_no == line_no)
    result = await db.execute(q)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    line_nos = [line.line_no for line in order.lines]

    md_result = await db.execute(
        select(MaterialDemand).where(
            MaterialDemand.order_no == order_no,
            MaterialDemand.line_no.in_(line_nos) if line_nos else False,
        )
    )
    materials = [MaterialDemandOut.model_validate(m) for m in md_result.scalars().all()]

    shortage_count = sum(1 for m in materials if m.shortage_flag)

    # Fetch bindings with PO details
    binding_result = await db.execute(
        select(OrderMaterialPoBinding)
        .options(selectinload(OrderMaterialPoBinding.purchase_order))
        .where(
            OrderMaterialPoBinding.order_no == order_no,
            OrderMaterialPoBinding.line_no.in_(line_nos) if line_nos else False,
        )
    )
    bindings = []
    for binding in binding_result.scalars().all():
        po_detail = None
        if binding.purchase_order:
            po_detail = PODetail.model_validate(binding.purchase_order)

        binding_out = BindingOut(
            id=binding.id,
            order_no=binding.order_no,
            line_no=binding.line_no,
            material_code=binding.material_code,
            po_no=binding.po_no,
            bound_qty=binding.bound_qty,
            bind_status=binding.bind_status,
            bind_source=binding.bind_source,
            po_detail=po_detail,
            created_at=binding.created_at,
        )
        bindings.append(binding_out)

    # Calculate in_transit_count and latest_eta from bindings
    in_transit_count = 0
    latest_eta = None
    today = date.today()
    for binding in bindings:
        if binding.po_detail and binding.po_detail.eta:
            po_status = binding.po_detail.po_status
            actual_arrival = binding.po_detail.actual_arrival_date
            eta = binding.po_detail.eta

            if (po_status not in ['received', 'cancelled'] and
                actual_arrival is None and
                eta >= today):
                in_transit_count += 1
                if latest_eta is None or eta > latest_eta:
                    latest_eta = eta

    # 查询该订单行的风险问题
    issue_result = await db.execute(
        select(RiskIssue).where(
            RiskIssue.order_no == order_no,
            RiskIssue.line_no.in_(line_nos) if line_nos else False,
        ).order_by(RiskIssue.created_at.desc())
    )
    issues = [RiskIssueOut.model_validate(i) for i in issue_result.scalars().all()]

    detail = OrderDetailOut(
        **SaleOrderOut.model_validate(order).model_dump(),
        lines=[SaleOrderLineOut.model_validate(line) for line in order.lines],
        material_demands=materials,
        bindings=bindings,
        shortage_count=shortage_count,
        in_transit_count=in_transit_count,
        latest_eta=latest_eta,
        issues=issues,
    )
    return ResponseModel(data=detail)


@router.post("", response_model=ResponseModel[SaleOrderOut])
async def create_order(
    data: OrderCreate,
    current_user: dict = Depends(PermissionChecker("orders.list", "create")),
    db: AsyncSession = Depends(get_db),
):
    exists = await db.execute(select(SaleOrder).where(SaleOrder.order_no == data.sale_order.order_no))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="订单号已存在")

    order = SaleOrder(**data.sale_order.model_dump())
    db.add(order)
    await db.flush()
    for line in data.lines:
        db.add(SaleOrderLine(order_no=order.order_no, **line.model_dump()))
    await db.flush()
    await log_audit(db, "sale_order", order.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(order)
    return ResponseModel(data=SaleOrderOut.model_validate(order))


@router.put("/{order_no}", response_model=ResponseModel[SaleOrderOut])
async def update_order(
    order_no: str,
    data: SaleOrderUpdate,
    current_user: dict = Depends(PermissionChecker("orders.list", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SaleOrder).where(SaleOrder.order_no == order_no)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "sale_order", order.id, "update", old_obj=order, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(order, field, value)
    await db.commit()
    await db.refresh(order)
    return ResponseModel(data=SaleOrderOut.model_validate(order))


# ── CSV导入 ──
@router.post("/import/inspection", response_model=ResponseModel)
async def import_inspection_csv_endpoint(
    filepath: str = Query(..., description="服务器上1.点检.csv的路径"),
    current_user: dict = Depends(PermissionChecker("orders.list", "import")),
    db: AsyncSession = Depends(get_db),
):
    """从1.点检.csv导入数据到SaleOrder表"""
    from app.services.order.import_csv import import_inspection_csv
    result = await import_inspection_csv(filepath, db)
    await log_audit(db, "sale_order", 0, "import", field_name="inspection_csv", new_value=filepath, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)


@router.post("/import/run-order", response_model=ResponseModel)
async def import_run_order_csv_endpoint(
    filepath: str = Query(..., description="服务器上2.跑单.csv的路径"),
    current_user: dict = Depends(PermissionChecker("orders.run_orders", "import")),
    db: AsyncSession = Depends(get_db),
):
    """从2.跑单.csv导入数据到RunOrder表"""
    from app.services.order.import_csv import import_run_order_csv
    result = await import_run_order_csv(filepath, db)
    await log_audit(db, "run_order", 0, "import", field_name="run_order_csv", new_value=filepath, operator=current_user["username"])
    await db.commit()
    return ResponseModel(data=result)
