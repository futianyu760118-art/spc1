from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.production.monthly_capacity_scenario import MonthlyCapacityScenario
from app.schemas.common import ResponseModel
from app.services.production.monthly_capacity_plan_service import (
    activate_monthly_schedule_batch,
    build_daily_allocation_preview,
    generate_monthly_schedule_plans,
    get_ai_allocation_preview,
    get_monthly_capacity_plan,
    list_monthly_schedule_batches,
    list_monthly_schedule_plans,
    update_monthly_schedule_plan,
)

router = APIRouter()

SCENARIO_ID = 1


class MonthlyPlanScenarioIn(BaseModel):
    workdays: int = Field(..., ge=1, le=31)
    daily_hours: float = Field(..., ge=1, le=24)
    assembly_manpower: int = Field(..., ge=1, le=500)
    packaging_manpower: int = Field(..., ge=1, le=500)
    include_sunday: bool = False
    include_scheduled: bool = True


def _serialize_scenario(scenario: MonthlyCapacityScenario) -> dict:
    return {
        "workdays": scenario.workdays,
        "daily_hours": float(scenario.daily_hours),
        "assembly_manpower": scenario.assembly_manpower,
        "packaging_manpower": scenario.packaging_manpower,
        "include_sunday": bool(scenario.include_sunday),
        "include_scheduled": bool(scenario.include_scheduled),
        "updated_by": scenario.updated_by,
        "updated_at": scenario.updated_at.isoformat() if scenario.updated_at else None,
    }


@router.get("/scenario", response_model=ResponseModel[dict])
async def get_monthly_plan_scenario(
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "read")
    ),
    db: AsyncSession = Depends(get_db),
):
    scenario = await db.get(MonthlyCapacityScenario, SCENARIO_ID)
    return ResponseModel(data=_serialize_scenario(scenario) if scenario else {})


@router.put("/scenario", response_model=ResponseModel[dict])
async def update_monthly_plan_scenario(
    payload: MonthlyPlanScenarioIn,
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "read")
    ),
    db: AsyncSession = Depends(get_db),
):
    scenario = await db.get(MonthlyCapacityScenario, SCENARIO_ID)
    if not scenario:
        scenario = MonthlyCapacityScenario(id=SCENARIO_ID)
        db.add(scenario)
    scenario.workdays = payload.workdays
    scenario.daily_hours = payload.daily_hours
    scenario.assembly_manpower = payload.assembly_manpower
    scenario.packaging_manpower = payload.packaging_manpower
    scenario.include_sunday = payload.include_sunday
    scenario.include_scheduled = payload.include_scheduled
    scenario.updated_by = current_user.get("username")
    scenario.updated_at = datetime.now()
    await db.flush()
    return ResponseModel(data=_serialize_scenario(scenario))


@router.get("", response_model=ResponseModel[dict])
async def monthly_capacity_plan(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    stage: str = Query("all", pattern="^(all|assembly|packaging)$"),
    workdays: int = Query(26, ge=1, le=31),
    daily_hours: float = Query(12.0, ge=1, le=24),
    assembly_manpower: int = Query(14, ge=1, le=500),
    packaging_manpower: int = Query(14, ge=1, le=500),
    include_sunday: bool = Query(False),
    include_scheduled: bool = Query(True),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "read")
    ),
    db: AsyncSession = Depends(get_db),
):
    """月度产能预算（只读，不写排产计划）。"""
    data = await get_monthly_capacity_plan(
        db,
        year=year,
        month=month,
        stage=stage,
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        include_sunday=include_sunday,
        include_scheduled=include_scheduled,
        keyword=keyword,
    )
    return ResponseModel(data=data)

@router.get("/allocation-preview", response_model=ResponseModel[dict])
async def monthly_capacity_allocation_preview(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    stage: str = Query("all", pattern="^(all|assembly|packaging)$"),
    workdays: int = Query(26, ge=1, le=31),
    daily_hours: float = Query(12.0, ge=1, le=24),
    assembly_manpower: int = Query(14, ge=1, le=500),
    packaging_manpower: int = Query(14, ge=1, le=500),
    include_sunday: bool = Query(False),
    include_scheduled: bool = Query(True),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "read")
    ),
    db: AsyncSession = Depends(get_db),
):
    """按月度参数生成每日分配预览（只读，不写排产计划）。"""
    plan = await get_monthly_capacity_plan(
        db,
        year=year,
        month=month,
        stage=stage,
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        include_sunday=include_sunday,
        include_scheduled=include_scheduled,
        keyword=keyword,
    )
    preview = build_daily_allocation_preview(
        plan,
        stage=stage,
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        include_sunday=include_sunday,
    )
    return ResponseModel(data={"summary": plan.get("summary"), "stages": plan.get("stages"), **preview})


@router.get("/ai-allocation-preview", response_model=ResponseModel[dict])
async def monthly_capacity_ai_allocation_preview(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    stage: str = Query("all", pattern="^(all|assembly|packaging)$"),
    workdays: int = Query(26, ge=1, le=31),
    daily_hours: float = Query(12.0, ge=1, le=24),
    assembly_manpower: int = Query(14, ge=1, le=500),
    packaging_manpower: int = Query(14, ge=1, le=500),
    include_sunday: bool = Query(False),
    include_scheduled: bool = Query(True),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "read")
    ),
    db: AsyncSession = Depends(get_db),
):
    """AI 决定订单行排产顺序，容量分摊后返回每日预览（只读，不写排产计划）。"""
    try:
        data = await get_ai_allocation_preview(
            db,
            year=year,
            month=month,
            stage=stage,
            workdays=workdays,
            daily_hours=daily_hours,
            assembly_manpower=assembly_manpower,
            packaging_manpower=packaging_manpower,
            include_sunday=include_sunday,
            include_scheduled=include_scheduled,
            keyword=keyword,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ResponseModel(data=data)


class MonthlyPlanUpdateIn(BaseModel):
    plan_date: Optional[date] = None
    daily_work_hours: Optional[float] = None
    schedule_bucket: Optional[str] = Field(None, pattern="^(assembly|packaging)$")


@router.post("/plans/generate", response_model=ResponseModel[dict])
async def generate_monthly_plan(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    workdays: int = Query(26, ge=1, le=31),
    daily_hours: float = Query(12.0, ge=1, le=24),
    assembly_manpower: int = Query(14, ge=1, le=500),
    packaging_manpower: int = Query(14, ge=1, le=500),
    include_sunday: bool = Query(False),
    include_scheduled: bool = Query(True),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    """按当前场景生成独立的月度排产方案（不碰原排产计划）。"""
    result = await generate_monthly_schedule_plans(
        db,
        year=year,
        month=month,
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        operator=current_user["username"],
        include_sunday=include_sunday,
        include_scheduled=include_scheduled,
    )
    return ResponseModel(data=result)


class AiScheduleOrderKeyIn(BaseModel):
    order_no: str
    line_no: str


class AiMonthlyPlanGenerateIn(BaseModel):
    order_sequence: list[AiScheduleOrderKeyIn] = Field(default_factory=list)


@router.post("/plans/generate-ai", response_model=ResponseModel[dict])
async def generate_ai_monthly_plan(
    payload: AiMonthlyPlanGenerateIn,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    workdays: int = Query(26, ge=1, le=31),
    daily_hours: float = Query(12.0, ge=1, le=24),
    assembly_manpower: int = Query(14, ge=1, le=500),
    packaging_manpower: int = Query(14, ge=1, le=500),
    include_sunday: bool = Query(False),
    include_scheduled: bool = Query(True),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    """按 AI 预览确认的订单行顺序生成独立月度排产批次（确定性容量分摊）。"""
    order_sequence = [
        (item.order_no.strip(), item.line_no.strip())
        for item in payload.order_sequence
        if item.order_no.strip()
    ]
    result = await generate_monthly_schedule_plans(
        db,
        year=year,
        month=month,
        workdays=workdays,
        daily_hours=daily_hours,
        assembly_manpower=assembly_manpower,
        packaging_manpower=packaging_manpower,
        operator=current_user["username"],
        include_sunday=include_sunday,
        include_scheduled=include_scheduled,
        order_sequence=order_sequence,
        scheme_label="AI月度排产方案",
    )
    return ResponseModel(data=result)


@router.get("/plans/batches", response_model=ResponseModel[list[dict]])
async def monthly_plan_batches(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "read")
    ),
    db: AsyncSession = Depends(get_db),
):
    items = await list_monthly_schedule_batches(db, year=year, month=month)
    return ResponseModel(data=items)


@router.post("/plans/batches/{batch_no}/activate", response_model=ResponseModel[dict])
async def activate_monthly_plan_batch(
    batch_no: str,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await activate_monthly_schedule_batch(
            db, year=year, month=month, batch_no=batch_no
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ResponseModel(data=data)


@router.get("/plans", response_model=ResponseModel[list[dict]])
async def monthly_plan_list(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    stage: str = Query("all", pattern="^(all|assembly|packaging)$"),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    keyword: Optional[str] = Query(None),
    batch_no: Optional[str] = Query(None),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "read")
    ),
    db: AsyncSession = Depends(get_db),
):
    items = await list_monthly_schedule_plans(
        db,
        year=year,
        month=month,
        stage=stage,
        date_start=date_start,
        date_end=date_end,
        keyword=keyword,
        batch_no=batch_no,
    )
    return ResponseModel(data=items)


@router.put("/plans/{plan_id}", response_model=ResponseModel[dict])
async def update_monthly_plan(
    plan_id: int,
    payload: MonthlyPlanUpdateIn,
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await update_monthly_schedule_plan(
            db,
            plan_id=plan_id,
            plan_date=payload.plan_date,
            daily_work_hours=payload.daily_work_hours,
            schedule_bucket=payload.schedule_bucket,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ResponseModel(data=data)
