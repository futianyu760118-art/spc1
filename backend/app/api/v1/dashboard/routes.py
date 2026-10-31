from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.material.material_demand import MaterialDemand
from app.schemas.common import ResponseModel, PageResult
from app.schemas.dashboard.schemas import (
    DashboardData, RiskSummary, OrderRiskRow, RiskDistribution,
    TodayOverview, TodayDueOrder,
    RollingRiskData,
    OrderRiskDistributionData,
    ClosureAchievement,
    ProcurementBoardData,
    ShipmentBoardData,
)
from app.schemas.order.schemas import MaterialDemandOut
from app.services.dashboard.dashboard_service import DashboardService

router = APIRouter()


@router.get("/summary", response_model=ResponseModel[DashboardData])
async def get_dashboard_summary(
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    data = await service.get_summary()
    return ResponseModel(data=data)


@router.get("/today-overview", response_model=ResponseModel[TodayOverview])
async def get_today_overview(
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    """供应链驾驶舱 — 今日总览"""
    service = DashboardService(db)
    data = await service.get_today_overview()
    return ResponseModel(data=data)


@router.get("/today-due-orders", response_model=ResponseModel[PageResult[TodayDueOrder]])
async def get_today_due_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    """供应链驾驶舱 — 今日应交订单列表"""
    service = DashboardService(db)
    result = await service.get_today_due_orders(page=page, page_size=page_size)
    return ResponseModel(data=result)


@router.get("/rolling-risk", response_model=ResponseModel[RollingRiskData])
async def get_rolling_risk(
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    """供应链驾驶舱 — 14天滚动风险"""
    service = DashboardService(db)
    data = await service.get_rolling_risk()
    return ResponseModel(data=data)


@router.get("/order-risk-distribution", response_model=ResponseModel[OrderRiskDistributionData])
async def get_order_risk_distribution(
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    """供应链驾驶舱 — 订单风险分布"""
    service = DashboardService(db)
    data = await service.get_order_risk_distribution()
    return ResponseModel(data=data)


@router.get("/closure-achievement", response_model=ResponseModel[ClosureAchievement])
async def get_closure_achievement(
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    """供应链驾驶舱 — 闭环达成看板"""
    service = DashboardService(db)
    data = await service.get_closure_achievement()
    return ResponseModel(data=data)


@router.get("/orders", response_model=ResponseModel[PageResult[OrderRiskRow]])
async def get_dashboard_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    data_source: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    result = await service.get_order_risk_list(
        page=page, page_size=page_size,
        risk_level=risk_level, owner=owner, keyword=keyword,
        status=status, data_source=data_source,
    )
    return ResponseModel(data=result)


@router.get("/materials", response_model=ResponseModel[PageResult[MaterialDemandOut]])
async def get_dashboard_materials(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    shortage_only: bool = Query(False, description="仅显示欠料"),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    """供应链驾驶舱 — 物料需求视图"""
    query = select(MaterialDemand)
    count_query = select(func.count(MaterialDemand.id))

    if shortage_only:
        query = query.where(MaterialDemand.shortage_flag == True)
        count_query = count_query.where(MaterialDemand.shortage_flag == True)
    if keyword:
        like_expr = f"%{keyword}%"
        query = query.where(
            (MaterialDemand.material_code.ilike(like_expr)) |
            (MaterialDemand.material_name.ilike(like_expr)) |
            (MaterialDemand.order_no.ilike(like_expr))
        )
        count_query = count_query.where(
            (MaterialDemand.material_code.ilike(like_expr)) |
            (MaterialDemand.material_name.ilike(like_expr)) |
            (MaterialDemand.order_no.ilike(like_expr))
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(MaterialDemand.shortage_flag.desc(), MaterialDemand.shortage_qty.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = [MaterialDemandOut.model_validate(m) for m in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.get("/risk-distribution", response_model=ResponseModel[list[RiskDistribution]])
async def get_risk_distribution(
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    data = await service.get_risk_distribution()
    return ResponseModel(data=data)


@router.get("/procurement-board", response_model=ResponseModel[ProcurementBoardData])
async def get_procurement_board(
    target_date: Optional[str] = Query(None, description="目标日期，格式 YYYY-MM-DD，默认今天"),
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    """供应链驾驶舱 — 采购看板（大屏）"""
    target = date.fromisoformat(target_date) if target_date else None
    service = DashboardService(db)
    data = await service.get_procurement_board(target_date=target)
    return ResponseModel(data=data)


@router.get("/shipment-board", response_model=ResponseModel[ShipmentBoardData])
async def get_shipment_board(
    current_user: dict = Depends(PermissionChecker("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
):
    """供应链驾驶舱 — 出货计划看板（已逾期 + 今日）"""
    service = DashboardService(db)
    data = await service.get_shipment_board()
    return ResponseModel(data=data)
