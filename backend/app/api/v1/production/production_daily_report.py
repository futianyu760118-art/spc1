"""生产协同中心 — 生产日报表 API（ERP/OA 同步数据，只读列表）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.production.production_daily_report import ProductionDailyReport
from app.schemas.common import ResponseModel, PageResult
from app.schemas.production.schemas import ProductionDailyReportOut

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[ProductionDailyReportOut]])
async def list_daily_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    report_date_from: Optional[date] = Query(None, description="日期起"),
    report_date_to: Optional[date] = Query(None, description="日期止"),
    workshop: Optional[str] = Query(None, description="车间筛选"),
    keyword: Optional[str] = Query(None, description="生产订单号/销售订单号/物料代码模糊搜索"),
    current_user: dict = Depends(PermissionChecker("production.daily_report", "read")),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if report_date_from:
        filters.append(ProductionDailyReport.report_date >= report_date_from)
    if report_date_to:
        filters.append(ProductionDailyReport.report_date <= report_date_to)
    if workshop:
        filters.append(ProductionDailyReport.workshop == workshop)
    if keyword:
        like = f"%{keyword}%"
        filters.append(
            or_(
                ProductionDailyReport.production_order_no.ilike(like),
                ProductionDailyReport.sale_order_no.ilike(like),
                ProductionDailyReport.material_code.ilike(like),
            )
        )

    count_stmt = select(func.count()).select_from(ProductionDailyReport)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar()

    query = (
        select(ProductionDailyReport)
        .where(*filters)
        .order_by(
            ProductionDailyReport.report_date.desc().nullslast(),
            ProductionDailyReport.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = [ProductionDailyReportOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total or 0, page=page, page_size=page_size, items=items))
