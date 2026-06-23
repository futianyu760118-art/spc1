"""Production schedule plan API."""

from datetime import date, datetime, timedelta
from typing import Optional, List
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.production.schedule_plan import ProductionSchedulePlan
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.production.product_process_capacity import ProductProcessCapacity
from app.models.rules.node_standard import NodeStandard
from app.schemas.common import PageResult, ResponseModel
from app.schemas.production.schemas import (
    ProductionSchedulePlanCreate,
    ProductionSchedulePlanOut,
    ProductionSchedulePlanUpdate,
    OrderForSchedulingOut,
    AutoScheduleRequest,
    AutoScheduleResponse,
    SaleOrderLineChangeLogOut,
)
from app.services.production.production_change_service import ProductionChangeService

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[ProductionSchedulePlanOut]])
async def list_schedule_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    keyword: Optional[str] = Query(None),
    needs_reschedule: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(True),
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if department:
        conditions.append(ProductionSchedulePlan.department == department)
    if status:
        conditions.append(ProductionSchedulePlan.status == status)
    if date_start:
        conditions.append(ProductionSchedulePlan.plan_date >= date_start)
    if date_end:
        conditions.append(ProductionSchedulePlan.plan_date <= date_end)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            or_(
                ProductionSchedulePlan.order_no.ilike(like),
                ProductionSchedulePlan.product_code.ilike(like),
                ProductionSchedulePlan.model_code.ilike(like),
                ProductionSchedulePlan.owner.ilike(like),
                ProductionSchedulePlan.remark.ilike(like),
            )
        )
    if needs_reschedule is not None:
        conditions.append(ProductionSchedulePlan.needs_reschedule == needs_reschedule)
    if is_active is not None:
        conditions.append(ProductionSchedulePlan.is_active == is_active)

    total = (await db.execute(select(func.count(ProductionSchedulePlan.id)).where(*conditions))).scalar() or 0
    result = await db.execute(
        select(ProductionSchedulePlan)
        .where(*conditions)
        .order_by(ProductionSchedulePlan.plan_date.desc(), ProductionSchedulePlan.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [ProductionSchedulePlanOut.model_validate(row) for row in result.scalars().all()]
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.post("", response_model=ResponseModel[ProductionSchedulePlanOut])
async def create_schedule_plan(
    data: ProductionSchedulePlanCreate,
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "create")),
    db: AsyncSession = Depends(get_db),
):
    record = ProductionSchedulePlan(**data.model_dump(), created_by=current_user["username"])
    db.add(record)
    await db.flush()
    await log_audit(db, "production_schedule_plan", record.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(record)
    return ResponseModel(data=ProductionSchedulePlanOut.model_validate(record))


@router.put("/{record_id}", response_model=ResponseModel[ProductionSchedulePlanOut])
async def update_schedule_plan(
    record_id: int,
    data: ProductionSchedulePlanUpdate,
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "update")),
    db: AsyncSession = Depends(get_db),
):
    record = (await db.execute(select(ProductionSchedulePlan).where(ProductionSchedulePlan.id == record_id))).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="计划不存在")

    update_data = data.model_dump(exclude_unset=True)
    await log_audit(db, "production_schedule_plan", record.id, "update", old_obj=record, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(record, field, value)
    await db.commit()
    await db.refresh(record)
    return ResponseModel(data=ProductionSchedulePlanOut.model_validate(record))


@router.delete("/{record_id}", response_model=ResponseModel[dict])
async def delete_schedule_plan(
    record_id: int,
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "delete")),
    db: AsyncSession = Depends(get_db),
):
    record = (await db.execute(select(ProductionSchedulePlan).where(ProductionSchedulePlan.id == record_id))).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="计划不存在")

    await log_audit(db, "production_schedule_plan", record.id, "delete", operator=current_user["username"])
    await db.delete(record)
    await db.commit()
    return ResponseModel(data={"deleted": record_id})


@router.post("/detect-changes", response_model=ResponseModel[List[SaleOrderLineChangeLogOut]])
async def detect_sale_order_line_changes(
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "update")),
    db: AsyncSession = Depends(get_db),
):
    """检测销售订单行变更并记录日志，同时标记相关排产计划需要重排"""
    service = ProductionChangeService(db)
    changed_logs = await service.detect_and_log_sale_order_line_changes()
    await db.commit()
    return ResponseModel(data=[log for log in changed_logs])


@router.post("/{plan_id}/reschedule", response_model=ResponseModel[ProductionSchedulePlanOut])
async def reschedule_plan(
    plan_id: int,
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "update")),
    db: AsyncSession = Depends(get_db),
):
    """重新排产一个已存在的计划"""
    # 1. 获取需要重排的旧计划
    old_plan_result = await db.execute(
        select(ProductionSchedulePlan).where(ProductionSchedulePlan.id == plan_id)
    )
    old_plan = old_plan_result.scalar_one_or_none()
    if not old_plan:
        raise HTTPException(status_code=404, detail="原排产计划不存在")
    
    # 2. 获取最新的销售订单行数据 (去重，只取最新的一条)
    sale_order_line_result = await db.execute(
        select(SaleOrderLine, SaleOrder.risk_level)
        .outerjoin(SaleOrder, SaleOrderLine.sale_order_id == SaleOrder.id)
        .where(and_(
            SaleOrderLine.order_no == old_plan.order_no,
            SaleOrderLine.line_no == old_plan.line_no,
        ))
        .order_by(SaleOrderLine.id.desc())
        .limit(1)
    )
    row = sale_order_line_result.first()
    if not row:
        raise HTTPException(status_code=404, detail="订单行不存在，无法重排")
    
    current_sale_order_line = row.SaleOrderLine
    risk_level = row.risk_level

    if not current_sale_order_line.promised_date:
        raise HTTPException(status_code=400, detail="订单行没有交期，无法重排")
    
    if not current_sale_order_line.order_qty or current_sale_order_line.order_qty <= 0:
        raise HTTPException(status_code=400, detail="订单行数量无效，无法重排")

    # 3. 确定UPPH (优先使用旧计划的UPPH，否则尝试产品UPPH)
    upph = old_plan.upph
    if upph is None and current_sale_order_line.product_code:
        # 计算综合 UPPH (直接累加)
        capacity_result = await db.execute(
            select(ProductProcessCapacity)
            .where(ProductProcessCapacity.product_code == current_sale_order_line.product_code)
        )
        
        total_upph = 0.0
        for c in capacity_result.scalars().all():
            if c.upph and float(c.upph) > 0:
                total_upph += float(c.upph)
                
        if total_upph > 0:
            upph = total_upph
    
    if upph is None or upph <= 0:
        raise HTTPException(status_code=400, detail="缺少UPPH数据，请在订单或产品中配置，或手动指定")

    # 4. 获取每日工作时间
    daily_hours = old_plan.daily_work_hours
    if daily_hours is None:
        config_result = await db.execute(select(NodeStandard).where(NodeStandard.node_code == "daily_work_hours"))
        config_item = config_result.scalar_one_or_none()
        daily_hours = float(config_item.time_value) if config_item else 8

    if daily_hours <= 0:
        raise HTTPException(status_code=400, detail="每日工作时间必须大于0")

    # 5. 计算排产时间
    total_hours = float(current_sale_order_line.order_qty) / float(upph)
    days_needed = math.ceil(total_hours / float(daily_hours))
    
    # 交期倒推
    end_date = current_sale_order_line.promised_date
    start_date = end_date - timedelta(days=days_needed - 1)
    
    # 确保开始日期不早于今天，如果早于今天，则改为顺推
    today = date.today()
    warning = ""
    if start_date < today:
        start_date = today
        end_date = start_date + timedelta(days=days_needed - 1)
        warning = f"【延期预警】按产能顺推，预计完工日期({end_date})晚于承诺交期({current_sale_order_line.promised_date})！"

    # 6. 确定优先级
    priority_map = {
        "red": "urgent",
        "yellow": "high",
        "blue": "normal",
        "green": "low",
    }
    priority = priority_map.get(risk_level or "green", "normal")

    # 7. 创建新的排产计划版本
    new_plan_version = old_plan.plan_version + 1
    plan_date = date.today() # 重排日期为今天

    new_schedule_data = ProductionSchedulePlanCreate(
        department=old_plan.department,
        plan_date=plan_date,
        order_no=current_sale_order_line.order_no,
        line_no=current_sale_order_line.line_no,
        product_code=current_sale_order_line.product_code,
        model_code=current_sale_order_line.product_model,
        quantity=float(current_sale_order_line.order_qty or 0),
        start_date=start_date,
        end_date=end_date,
        priority=priority,
        status="planned", # 重排后状态仍为planned
        upph=upph,
        daily_work_hours=daily_hours,
        owner=old_plan.owner, # 沿用旧计划的负责人
        remark=f"重排：{warning if warning else ''}原计划ID:{old_plan.id}, 原因:{old_plan.reschedule_reason}",
        
        # 快照数据 (使用最新的订单行数据作为快照)
        plan_version=new_plan_version,
        is_active=True,
        source_promised_date=current_sale_order_line.promised_date,
        source_order_qty=float(current_sale_order_line.order_qty or 0),
        source_product_code=current_sale_order_line.product_code,
        source_product_model=current_sale_order_line.product_model,
        source_upph=upph,
        previous_plan_id=old_plan.id,
        needs_reschedule=False, # 新计划不需要重排
        reschedule_reason=None,
    )
    
    new_record = ProductionSchedulePlan(**new_schedule_data.model_dump(), created_by=current_user["username"])
    db.add(new_record)

    # 8. 标记旧计划为非活跃
    old_plan.is_active = False
    old_plan.needs_reschedule = False
    old_plan.reschedule_reason = "已重排"
    db.add(old_plan)

    await db.flush()
    await log_audit(db, "production_schedule_plan", new_record.id, "reschedule", operator=current_user["username"], old_obj=old_plan)
    await db.commit()
    await db.refresh(new_record)
    
    return ResponseModel(data=ProductionSchedulePlanOut.model_validate(new_record))


# ============ 一键排产相关API ============

@router.get("/orders-for-scheduling", response_model=ResponseModel[PageResult[OrderForSchedulingOut]])
async def list_orders_for_scheduling(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    only_unscheduled: bool = Query(False),
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "read")),
    db: AsyncSession = Depends(get_db),
):
    """获取当月交期的订单列表，用于排产"""
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month
    
    first_day = date(target_year, target_month, 1)
    if target_month == 12:
        last_day = date(target_year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(target_year, target_month + 1, 1) - timedelta(days=1)
    
    conditions = [
        SaleOrderLine.promised_date >= first_day,
        SaleOrderLine.promised_date <= last_day,
        SaleOrderLine.status != "closed",
    ]
    
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            or_(
                SaleOrderLine.order_no.ilike(like),
                SaleOrderLine.product_code.ilike(like),
            )
        )
    
    # Note: risk_level is on SaleOrder, we might need a join if we want to filter by it
    # For now, we'll skip risk_level filtering on lines or join with SaleOrder
    
    # 使用子查询去重，只取每个 order_no + line_no 的最新一条
    subq = (
        select(
            SaleOrderLine.order_no,
            SaleOrderLine.line_no,
            func.max(SaleOrderLine.id).label('max_id')
        )
        .where(*conditions)
        .group_by(SaleOrderLine.order_no, SaleOrderLine.line_no)
        .subquery()
    )

    total = (await db.execute(select(func.count()).select_from(subq))).scalar() or 0
    
    result = await db.execute(
        select(SaleOrderLine, SaleOrder.customer, SaleOrder.risk_level)
        .join(
            subq,
            and_(
                SaleOrderLine.order_no == subq.c.order_no,
                SaleOrderLine.line_no == subq.c.line_no,
                SaleOrderLine.id == subq.c.max_id
            )
        )
        .outerjoin(SaleOrder, SaleOrderLine.sale_order_id == SaleOrder.id)
        .order_by(SaleOrderLine.promised_date.asc(), SaleOrderLine.order_no.asc(), SaleOrderLine.line_no.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    
    rows = result.all()
    
    # 查询所有相关产品的UPPH，并计算综合UPPH (直接累加法)
    product_codes = [row.SaleOrderLine.product_code for row in rows if row.SaleOrderLine.product_code]
    product_upph_map = {}
    if product_codes:
        capacity_result = await db.execute(
            select(ProductProcessCapacity)
            .where(ProductProcessCapacity.product_code.in_(product_codes))
        )
        
        # 按产品编码分组，直接累加 UPPH
        for c in capacity_result.scalars().all():
            if c.upph and float(c.upph) > 0:
                product_upph_map[c.product_code] = product_upph_map.get(c.product_code, 0.0) + float(c.upph)
    
    # 查询已有排产计划的订单行
    order_nos = [row.SaleOrderLine.order_no for row in rows]
    line_nos = [row.SaleOrderLine.line_no for row in rows]
    scheduled_set = set()
    if order_nos and line_nos:
        schedule_result = await db.execute(
            select(ProductionSchedulePlan.order_no, ProductionSchedulePlan.line_no)
            .where(
                ProductionSchedulePlan.order_no.in_(order_nos),
                ProductionSchedulePlan.line_no.in_(line_nos),
                ProductionSchedulePlan.is_active == True
            )
        )
        for order_no, line_no in schedule_result.all():
            scheduled_set.add(f"{order_no}_{line_no}")
    
    items = []
    for row in rows:
        order_line = row.SaleOrderLine
        customer = row.customer
        risk_level = row.risk_level
        
        has_schedule = f"{order_line.order_no}_{order_line.line_no}" in scheduled_set
        if only_unscheduled and has_schedule:
            continue
            
        items.append(OrderForSchedulingOut(
            order_no=order_line.order_no,
            line_no=order_line.line_no,
            customer=customer,
            product_code=order_line.product_code,
            product_model=order_line.product_model,
            order_qty=float(order_line.order_qty or 0),
            promised_date=order_line.promised_date,
            risk_level=risk_level,
            status=order_line.status,
            upph=product_upph_map.get(order_line.product_code, 0) if order_line.product_code else 0,
            has_schedule=has_schedule,
        ))
    
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.get("/work-hours-config", response_model=ResponseModel[dict])
async def get_work_hours_config(
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "read")),
    db: AsyncSession = Depends(get_db),
):
    """获取每日工作时间配置"""
    config = await db.execute(select(NodeStandard).where(NodeStandard.node_code == "daily_work_hours"))
    config_item = config.scalar_one_or_none()
    return ResponseModel(data={
        "daily_work_hours": float(config_item.time_value) if config_item else 8
    })


@router.post("/auto-schedule", response_model=ResponseModel[AutoScheduleResponse])
async def auto_schedule(
    data: AutoScheduleRequest,
    current_user: dict = Depends(PermissionChecker("production.schedule_plans", "create")),
    db: AsyncSession = Depends(get_db),
):
    """一键排产"""
    # 1. 获取订单信息 (去重，只取最新的一条)
    order_result = await db.execute(
        select(SaleOrderLine, SaleOrder.risk_level)
        .outerjoin(SaleOrder, SaleOrderLine.sale_order_id == SaleOrder.id)
        .where(and_(
            SaleOrderLine.order_no == data.order_no,
            SaleOrderLine.line_no == data.line_no,
        ))
        .order_by(SaleOrderLine.id.desc())
        .limit(1)
    )
    row = order_result.first()
    if not row:
        raise HTTPException(status_code=404, detail="订单行不存在")
    
    order_line = row.SaleOrderLine
    risk_level = row.risk_level
    
    if not order_line.promised_date:
        raise HTTPException(status_code=400, detail="订单行没有交期")
    
    if not order_line.order_qty or order_line.order_qty <= 0:
        raise HTTPException(status_code=400, detail="订单行数量无效")
    
    # 2. 获取或使用指定的UPPH
    upph = data.upph
    if upph is None and order_line.product_code:
        capacity_result = await db.execute(
            select(ProductProcessCapacity)
            .where(ProductProcessCapacity.product_code == order_line.product_code)
        )
        
        total_upph = 0.0
        for c in capacity_result.scalars().all():
            if c.upph and float(c.upph) > 0:
                total_upph += float(c.upph)
                
        if total_upph > 0:
            upph = total_upph
    
    if upph is None or upph <= 0:
        raise HTTPException(status_code=400, detail="缺少UPPH数据，请在订单或产品中配置，或手动指定")
    
    # 3. 获取每日工作时间
    daily_hours = data.daily_work_hours
    if daily_hours is None:
        config_result = await db.execute(select(NodeStandard).where(NodeStandard.node_code == "daily_work_hours"))
        config_item = config_result.scalar_one_or_none()
        daily_hours = float(config_item.time_value) if config_item else 8
    
    if daily_hours <= 0:
        raise HTTPException(status_code=400, detail="每日工作时间必须大于0")
    
    # 4. 计算排产时间
    total_hours = float(order_line.order_qty) / float(upph)
    days_needed = math.ceil(total_hours / float(daily_hours))
    
    # 交期倒推
    end_date = order_line.promised_date
    start_date = end_date - timedelta(days=days_needed - 1)
    
    # 确保开始日期不早于今天，如果早于今天，则改为顺推
    today = date.today()
    warning = ""
    if start_date < today:
        start_date = today
        end_date = start_date + timedelta(days=days_needed - 1)
        warning = f"【延期预警】按产能顺推，预计完工日期({end_date})晚于承诺交期({order_line.promised_date})！"
    
    # 5. 确定优先级
    priority_map = {
        "red": "urgent",
        "yellow": "high",
        "blue": "normal",
        "green": "low",
    }
    priority = priority_map.get(risk_level or "green", "normal")
    
    # 6. 检查是否已有排产计划，处理版本
    existing_plan_result = await db.execute(
        select(ProductionSchedulePlan)
        .where(
            ProductionSchedulePlan.order_no == data.order_no,
            ProductionSchedulePlan.line_no == data.line_no,
            ProductionSchedulePlan.is_active == True
        )
    )
    existing_plan = existing_plan_result.scalar_one_or_none()
    
    plan_version = 1
    previous_plan_id = None
    if existing_plan:
        plan_version = existing_plan.plan_version + 1
        previous_plan_id = existing_plan.id
        existing_plan.is_active = False
        db.add(existing_plan)
    
    # 7. 创建排产计划
    plan_date = data.plan_date or today
    schedule_data = ProductionSchedulePlanCreate(
        department=data.department,
        plan_date=plan_date,
        order_no=order_line.order_no,
        line_no=order_line.line_no,
        product_code=order_line.product_code,
        model_code=order_line.product_model,
        quantity=float(order_line.order_qty),
        start_date=start_date,
        end_date=end_date,
        priority=priority,
        status="planned",
        upph=upph,
        daily_work_hours=daily_hours,
        owner=data.owner,
        remark=warning if warning else None,
        
        # 快照数据
        plan_version=plan_version,
        is_active=True,
        source_promised_date=order_line.promised_date,
        source_order_qty=float(order_line.order_qty),
        source_product_code=order_line.product_code,
        source_product_model=order_line.product_model,
        source_upph=upph,
        previous_plan_id=previous_plan_id,
    )
    
    record = ProductionSchedulePlan(**schedule_data.model_dump(), created_by=current_user["username"])
    db.add(record)
    await db.flush()
    await log_audit(db, "production_schedule_plan", record.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(record)
    
    calculation_result = {
        "total_hours": round(total_hours, 2),
        "days_needed": days_needed,
        "upph": upph,
        "daily_work_hours": daily_hours,
    }
    
    return ResponseModel(data=AutoScheduleResponse(
        success=True,
        message=warning or "排产成功",
        schedule_plan=ProductionSchedulePlanOut.model_validate(record),
        calculation_result=calculation_result,
    ))
