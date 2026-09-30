"""MRP K3 对比总览（只读）。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.mrp.run import MrpRun
from app.models.mrp.scheme import MrpScheme
from app.schemas.common import ResponseModel
from app.services.mrp.comparison import read_comparison

comparison_router = APIRouter()


@comparison_router.get("/comparison", response_model=ResponseModel[dict])
async def get_comparison(
    run_id: Optional[int] = Query(None),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    if run_id is None:
        run_id = (await db.execute(select(func.max(MrpRun.id)).where(MrpRun.status == "success"))).scalar()
    if run_id is None:
        raise HTTPException(status_code=404, detail="暂无成功的运算批次")
    run = (await db.execute(select(MrpRun).where(MrpRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="批次不存在")

    scheme = None
    if run.scheme_id:
        scheme = (await db.execute(select(MrpScheme).where(MrpScheme.id == run.scheme_id))).scalar_one_or_none()
    if scheme is None:
        scheme = (
            await db.execute(select(MrpScheme).where(MrpScheme.is_default.is_(True)).limit(1))
        ).scalar_one_or_none()
    if scheme is None:
        raise HTTPException(status_code=404, detail="计划方案不存在")

    return ResponseModel(data=await read_comparison(db, int(run_id), scheme))
