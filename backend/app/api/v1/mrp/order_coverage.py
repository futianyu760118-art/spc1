"""MRP 订单覆盖视图（只读）。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.mrp.order_coverage_service import build_order_coverage

order_coverage_router = APIRouter()


@order_coverage_router.get("/order-coverage", response_model=ResponseModel[dict])
async def get_order_coverage(
    order_no: str = Query(..., min_length=1, description="销售订单号"),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    data = await build_order_coverage(db, order_no)
    if not data["lines"]:
        raise HTTPException(status_code=404, detail="订单不存在或无未结行")
    return ResponseModel(data=data)
