"""物料齐套中心 — 供应商风险分析 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.core.supplier_scope import get_supplier_name_scope
from app.schemas.common import ResponseModel
from app.schemas.material.schemas import SupplierRiskItem
from app.services.material.supplier_risk_service import get_supplier_risk

router = APIRouter()


@router.get("", response_model=ResponseModel[list[SupplierRiskItem]])
async def supplier_risk(
    supplier: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.supplier_risk", "read")),
    db: AsyncSession = Depends(get_db),
):
    supplier_scope = await get_supplier_name_scope(current_user, db)
    items = await get_supplier_risk(
        db,
        supplier=supplier_scope or supplier,
        exact_supplier=bool(supplier_scope),
        risk_level=risk_level,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return ResponseModel(data=items)
