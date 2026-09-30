"""MRP 总览聚合（只读）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.mrp.overview_service import build_overview

overview_router = APIRouter()


@overview_router.get("/overview", response_model=ResponseModel[dict])
async def get_overview(
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await build_overview(db))
