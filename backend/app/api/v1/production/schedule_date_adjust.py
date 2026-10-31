"""手工改日期路由.

独立于排产台账的「日期调整」入口:
- 以手工日期为准, 硬排, 不级联推后其它计划
- 改完立刻重算产能槽, 看板按新槽展示
- 产能超限只返回冲突清单, 不阻止保存
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.production.schedule_plans import (
    _invalidate_schedule_runtime_caches,
    _log_schedule_operation,
    _sync_snapshot_schedule_state_for_keys,
)
from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.production.schedule_plan import ProductionSchedulePlan
from app.schemas.common import ResponseModel
from app.schemas.production.schemas import (
    InsertSchedulePlanRequest,
    InsertSchedulePlanResponse,
    ManualDateAdjustItemOut,
    ManualDateAdjustRequest,
    ManualDateAdjustResponse,
    ProductionSchedulePlanOut,
    PushedPlanOut,
    ScheduleRemainderOut,
    SplitSchedulePlanRequest,
    SplitSchedulePlanResponse,
)
from app.services.production.manual_date_adjust_service import (
    adjust_plan_date,
    detect_capacity_conflicts,
)
from app.services.production.plan_insert_service import (
    insert_schedule_plan,
    split_schedule_plan,
)
from app.services.production.kpi_summary_service import invalidate_kpi_cache

logger = logging.getLogger(__name__)

router = APIRouter()

ADJUSTABLE_STATUSES = {"planned", "in_progress", "delayed"}


@router.post("/batch", response_model=ResponseModel[ManualDateAdjustResponse])
async def batch_adjust_schedule_dates(
    payload: ManualDateAdjustRequest,
    current_user: dict = Depends(PermissionChecker("production.schedule_date_adjust", "update")),
    db: AsyncSession = Depends(get_db),
):
    """批量改排产日期（硬排）.

    每条计划独立 SAVEPOINT: 单条失败不影响其它条.
    返回成功明细 + 当天产能超限清单.
    """
    operator = current_user["username"]
    results: list[ManualDateAdjustItemOut] = []
    adjusted_plan_ids: list[int] = []
    adjusted_keys: set[tuple[str, str]] = set()

    for item in payload.items:
        plan = (
            await db.execute(
                select(ProductionSchedulePlan).where(
                    ProductionSchedulePlan.id == item.plan_id
                )
            )
        ).scalar_one_or_none()

        if not plan or not plan.is_active:
            results.append(ManualDateAdjustItemOut(
                plan_id=item.plan_id,
                target_date=item.target_date,
                success=False,
                message="计划不存在或已失效",
            ))
            continue
        if plan.status not in ADJUSTABLE_STATUSES:
            results.append(ManualDateAdjustItemOut(
                plan_id=item.plan_id,
                order_no=plan.order_no,
                line_no=plan.line_no,
                target_date=item.target_date,
                success=False,
                message=f"状态 {plan.status} 不允许改期",
            ))
            continue

        old_plan_date = plan.plan_date
        try:
            async with db.begin_nested():
                result = await adjust_plan_date(db, plan=plan, target_date=item.target_date)
                await log_audit(
                    db,
                    "production_schedule_plan",
                    plan.id,
                    "update",
                    operator=operator,
                    update_data={
                        "plan_date": item.target_date,
                        "previous_plan_date": old_plan_date,
                    },
                )
                await _log_schedule_operation(
                    db,
                    "manual_date_adjust",
                    operator,
                    plan_id=plan.id,
                    plan_version=plan.plan_version,
                    order_no=plan.order_no,
                    line_no=plan.line_no,
                    remark=payload.reason or f"手工改日期 {old_plan_date} -> {item.target_date}",
                )
        except ValueError as e:
            results.append(ManualDateAdjustItemOut(
                plan_id=item.plan_id,
                order_no=plan.order_no,
                line_no=plan.line_no,
                target_date=item.target_date,
                success=False,
                message=str(e),
            ))
            continue
        except Exception as e:
            logger.exception("手工改日期失败 plan_id=%s", item.plan_id)
            results.append(ManualDateAdjustItemOut(
                plan_id=item.plan_id,
                order_no=plan.order_no,
                line_no=plan.line_no,
                target_date=item.target_date,
                success=False,
                message=f"改期失败: {e}",
            ))
            continue

        results.append(ManualDateAdjustItemOut(**result))
        adjusted_plan_ids.append(plan.id)
        if plan.order_no and plan.line_no:
            adjusted_keys.add((plan.order_no, plan.line_no))

    conflicts = await detect_capacity_conflicts(db, plan_ids=adjusted_plan_ids)
    await db.commit()

    if adjusted_keys:
        try:
            await _sync_snapshot_schedule_state_for_keys(db, adjusted_keys)
        except Exception:
            await db.rollback()
            logger.warning(
                "手工改日期后刷新订单快照失败（不影响已保存的日期）: %s",
                sorted(adjusted_keys),
                exc_info=True,
            )
    if adjusted_plan_ids:
        _invalidate_schedule_runtime_caches()
        invalidate_kpi_cache()

    success_count = sum(1 for item in results if item.success)
    response = ManualDateAdjustResponse(
        total=len(results),
        success_count=success_count,
        failed_count=len(results) - success_count,
        items=results,
        conflicts=conflicts,
    )
    return ResponseModel(data=response)


@router.post("/insert", response_model=ResponseModel[InsertSchedulePlanResponse])
async def insert_plan(
    payload: InsertSchedulePlanRequest,
    current_user: dict = Depends(PermissionChecker("production.schedule_date_adjust", "update")),
    db: AsyncSession = Depends(get_db),
):
    """插入一条计划（订单池新单或同订单返单），同段后续计划整体顺延."""
    operator = current_user["username"]
    if not (payload.order_no or "").strip():
        raise HTTPException(status_code=400, detail="订单号不能为空")
    if not str(payload.line_no or "").strip():
        raise HTTPException(status_code=400, detail="行号不能为空")
    if not (payload.product_code or "").strip():
        raise HTTPException(status_code=400, detail="产品编码不能为空")
    try:
        plan_remark = payload.remark
        if payload.rework_request_id and not plan_remark:
            plan_remark = f"OA返工单 {payload.rework_request_id}"
        source_order_qty = payload.source_order_qty
        if payload.rework_request_id and source_order_qty is None:
            # OA 返工是额外工作量，不冲抵原订单的待排余量
            source_order_qty = payload.quantity
        async with db.begin_nested():
            plan, pushed, conflicts = await insert_schedule_plan(
                db,
                order_no=payload.order_no.strip(),
                line_no=str(payload.line_no or "1").strip(),
                department=payload.department,
                schedule_bucket=payload.schedule_bucket,
                target_date=payload.target_date,
                quantity=payload.quantity,
                upph=payload.upph,
                manpower=payload.manpower,
                daily_work_hours=payload.daily_work_hours,
                total_hours_override=payload.rework_hours,
                product_code=payload.product_code,
                model_code=payload.model_code,
                owner=payload.owner,
                priority=payload.priority,
                source_promised_date=payload.source_promised_date,
                allow_duplicate=payload.allow_duplicate,
                source_order_qty=source_order_qty,
                remark=plan_remark,
                break_frozen_reason=payload.break_frozen_reason,
                operator=operator,
            )
            await log_audit(
                db,
                "production_schedule_plan",
                plan.id,
                "create",
                operator=operator,
            )
            await _log_schedule_operation(
                db,
                "insert",
                operator,
                plan_id=plan.id,
                plan_version=plan.plan_version,
                order_no=plan.order_no,
                line_no=plan.line_no,
                remark=(
                    plan_remark
                    or f"插入计划 {payload.target_date}，顺延 {len(pushed)} 条"
                ),
                affected_plan_ids=[item["plan_id"] for item in pushed],
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()

    keys = {(plan.order_no, plan.line_no)} if plan.order_no and plan.line_no else set()
    if keys:
        try:
            await _sync_snapshot_schedule_state_for_keys(db, keys)
        except Exception:
            await db.rollback()
            logger.warning(
                "插单后刷新订单快照失败（不影响已保存的计划）: %s",
                sorted(keys),
                exc_info=True,
            )
    _invalidate_schedule_runtime_caches()
    invalidate_kpi_cache()
    await db.refresh(plan)

    response = InsertSchedulePlanResponse(
        plan=ProductionSchedulePlanOut.model_validate(plan),
        pushed=[PushedPlanOut(**item) for item in pushed],
        conflicts=conflicts,
    )
    return ResponseModel(data=response)


@router.post("/split", response_model=ResponseModel[SplitSchedulePlanResponse])
async def split_plan(
    payload: SplitSchedulePlanRequest,
    current_user: dict = Depends(PermissionChecker("production.schedule_date_adjust", "update")),
    db: AsyncSession = Depends(get_db),
):
    """把一个计划按数量拆成多批（支持只生产一部分）."""
    operator = current_user["username"]
    try:
        async with db.begin_nested():
            plans, pushed, unplanned_qty, conflicts = await split_schedule_plan(
                db,
                plan_id=payload.plan_id,
                batches=[item.model_dump() for item in payload.batches],
                push_conflicts=payload.push_conflicts,
                break_frozen_reason=payload.break_frozen_reason,
                operator=operator,
            )
            for plan in plans:
                await log_audit(
                    db,
                    "production_schedule_plan",
                    plan.id,
                    "create",
                    operator=operator,
                )
            await _log_schedule_operation(
                db,
                "split",
                operator,
                plan_id=plans[0].id if plans else payload.plan_id,
                plan_version=plans[0].plan_version if plans else None,
                order_no=plans[0].order_no if plans else None,
                line_no=plans[0].line_no if plans else None,
                remark=payload.break_frozen_reason
                or f"拆单为 {len(plans)} 批，未拆数量 {unplanned_qty:g}",
                affected_plan_ids=[plan.id for plan in plans],
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()

    keys = {
        (plan.order_no, plan.line_no)
        for plan in plans
        if plan.order_no and plan.line_no
    }
    if keys:
        try:
            await _sync_snapshot_schedule_state_for_keys(db, keys)
        except Exception:
            await db.rollback()
            logger.warning(
                "拆单后刷新订单快照失败（不影响已保存的计划）: %s",
                sorted(keys),
                exc_info=True,
            )
    _invalidate_schedule_runtime_caches()
    invalidate_kpi_cache()
    for plan in plans:
        await db.refresh(plan)

    response = SplitSchedulePlanResponse(
        plans=[ProductionSchedulePlanOut.model_validate(plan) for plan in plans],
        pushed=[PushedPlanOut(**item) for item in pushed],
        unplanned_qty=unplanned_qty,
        conflicts=conflicts,
    )
    return ResponseModel(data=response)


@router.get("/remainders", response_model=ResponseModel[List[ScheduleRemainderOut]])
async def list_schedule_remainders(
    department: Optional[str] = Query(None),
    schedule_bucket: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("production.schedule_date_adjust", "read")),
    db: AsyncSession = Depends(get_db),
):
    """已排计划未覆盖完的剩余量（拆单少排 / 只生产一部分）."""
    planned_expr = func.sum(
        func.coalesce(
            ProductionSchedulePlan.planned_qty,
            ProductionSchedulePlan.quantity,
        )
    )
    source_expr = func.max(ProductionSchedulePlan.source_order_qty)

    conditions = [
        ProductionSchedulePlan.is_active == True,
        ProductionSchedulePlan.order_no.isnot(None),
        ProductionSchedulePlan.line_no.isnot(None),
        ProductionSchedulePlan.source_order_qty.isnot(None),
        or_(
            ProductionSchedulePlan.planned_qty.isnot(None),
            ProductionSchedulePlan.quantity.isnot(None),
        ),
    ]
    if department:
        conditions.append(ProductionSchedulePlan.department == department)
    if schedule_bucket:
        conditions.append(ProductionSchedulePlan.source_process_type == schedule_bucket)

    rows = (
        await db.execute(
            select(
                ProductionSchedulePlan.order_no,
                ProductionSchedulePlan.line_no,
                ProductionSchedulePlan.source_process_type,
                func.max(ProductionSchedulePlan.department).label("department"),
                func.max(ProductionSchedulePlan.product_code).label("product_code"),
                func.max(ProductionSchedulePlan.model_code).label("model_code"),
                source_expr.label("source_order_qty"),
                planned_expr.label("planned_qty"),
                func.max(ProductionSchedulePlan.upph).label("upph"),
                func.max(ProductionSchedulePlan.manpower).label("manpower"),
                func.max(ProductionSchedulePlan.daily_work_hours).label("daily_work_hours"),
                func.max(ProductionSchedulePlan.plan_date).label("last_plan_date"),
            )
            .where(*conditions)
            .group_by(
                ProductionSchedulePlan.order_no,
                ProductionSchedulePlan.line_no,
                ProductionSchedulePlan.source_process_type,
                ProductionSchedulePlan.source_order_qty,
            )
            .having(source_expr - planned_expr > 0.01)
            .order_by(func.max(ProductionSchedulePlan.plan_date).asc())
            .limit(200)
        )
    ).all()

    items = []
    for row in rows:
        source_qty = float(row.source_order_qty or 0)
        planned_qty = float(row.planned_qty or 0)
        items.append(ScheduleRemainderOut(
            order_no=row.order_no,
            line_no=row.line_no,
            department=row.department,
            schedule_bucket=row.source_process_type,
            product_code=row.product_code,
            model_code=row.model_code,
            source_order_qty=source_qty,
            planned_qty=round(planned_qty, 2),
            remaining_qty=round(source_qty - planned_qty, 2),
            upph=float(row.upph) if row.upph is not None else None,
            manpower=int(row.manpower) if row.manpower is not None else None,
            daily_work_hours=(
                float(row.daily_work_hours) if row.daily_work_hours is not None else None
            ),
            last_plan_date=row.last_plan_date,
        ))
    return ResponseModel(data=items)
