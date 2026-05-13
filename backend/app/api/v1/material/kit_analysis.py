"""物料齐套中心 — 齐套分析 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.schemas.material.schemas import KitAnalysisItem, KitAnalysisMaterialItem
from app.services.material.kit_analysis_service import get_kit_analysis, get_order_materials

router = APIRouter()


@router.get("", response_model=ResponseModel[dict])
async def kit_analysis(
    order_no: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    only_pending_shipment: bool = Query(False, description="仅显示发货未完成的订单"),
    current_user: dict = Depends(PermissionChecker("materials.kit_analysis", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await get_kit_analysis(db, order_no=order_no, risk_level=risk_level, sort_by=sort_by, sort_order=sort_order, page=page, page_size=page_size, only_pending_shipment=only_pending_shipment)
    return ResponseModel(data=result)


@router.get("/{order_no}/materials", response_model=ResponseModel[list[KitAnalysisMaterialItem]])
async def order_materials(
    order_no: str,
    status: Optional[str] = Query(None, description="状态筛选"),
    supplier: Optional[str] = Query(None, description="供应商筛选"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.kit_analysis", "read")),
    db: AsyncSession = Depends(get_db),
):
    items = await get_order_materials(db, order_no=order_no, status_filter=status, supplier_filter=supplier, sort_by=sort_by, sort_order=sort_order)
    return ResponseModel(data=items)
