"""生产协同中心 — 372 驾驶舱 KPI 聚合 API

阶段 1a 最小版：接通 today + pending，frozen/material 返回 None，anomalies 空。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.production.kpi_summary_service import get_kpi_summary, get_today_cards

router = APIRouter()


@router.get("", response_model=ResponseModel)
async def get_kpi_summary_endpoint(
    current_user: dict = Depends(PermissionChecker("production.overview", "read")),
    db: AsyncSession = Depends(get_db),
):
    data = await get_kpi_summary(db)
    return ResponseModel(data=data)


@router.get("/today-cards", response_model=ResponseModel)
async def get_today_cards_endpoint(
    current_user: dict = Depends(PermissionChecker("production.overview", "read")),
    db: AsyncSession = Depends(get_db),
):
    data = await get_today_cards(db)
    return ResponseModel(data=data)
