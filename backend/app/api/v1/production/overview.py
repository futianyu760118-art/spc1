"""生产协同中心 — 生产总览 API"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.schemas.production.schemas import ProductionOverviewData
from app.services.production.production_overview_service import get_production_overview

router = APIRouter()


@router.get("", response_model=ResponseModel[ProductionOverviewData])
async def get_overview(
    current_user: dict = Depends(PermissionChecker("production.overview", "read")),
    db: AsyncSession = Depends(get_db),
):
    data = await get_production_overview(db)
    return ResponseModel(data=data)
