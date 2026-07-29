"""生产协同中心 — 工价审核数据 API（ERP 同步数据，只读列表）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.production.labor_price_audit import ProductionLaborPriceAudit
from app.schemas.common import ResponseModel, PageResult
from app.schemas.production.schemas import LaborPriceAuditOut

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[LaborPriceAuditOut]])
async def list_labor_price_audits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    apply_date_from: Optional[date] = Query(None, description="申请日期起"),
    apply_date_to: Optional[date] = Query(None, description="申请日期止"),
    valid_flag: Optional[int] = Query(None, description="有效标志筛选"),
    department_id: Optional[int] = Query(None, description="部门ID筛选"),
    keyword: Optional[str] = Query(None, description="单据编号/物料代码/工价表唯一码/BOM编码 模糊搜索"),
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if apply_date_from:
        filters.append(ProductionLaborPriceAudit.apply_date >= apply_date_from)
    if apply_date_to:
        filters.append(ProductionLaborPriceAudit.apply_date <= apply_date_to)
    if valid_flag is not None:
        filters.append(ProductionLaborPriceAudit.valid_flag == valid_flag)
    if department_id is not None:
        filters.append(ProductionLaborPriceAudit.department_id == department_id)
    if keyword:
        like = f"%{keyword}%"
        filters.append(
            or_(
                ProductionLaborPriceAudit.doc_no.ilike(like),
                ProductionLaborPriceAudit.material_code.ilike(like),
                ProductionLaborPriceAudit.labor_price_code.ilike(like),
                ProductionLaborPriceAudit.bom_code.ilike(like),
            )
        )

    count_stmt = select(func.count()).select_from(ProductionLaborPriceAudit)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar()

    query = (
        select(ProductionLaborPriceAudit)
        .where(*filters)
        .order_by(
            ProductionLaborPriceAudit.apply_date.desc().nullslast(),
            ProductionLaborPriceAudit.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = [LaborPriceAuditOut.model_validate(r) for r in result.scalars().all()]

    return ResponseModel(data=PageResult(total=total or 0, page=page, page_size=page_size, items=items))
