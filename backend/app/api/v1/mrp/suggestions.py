"""MRP 建议：列表 / 批量审核。"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.mrp.run import MrpRun
from app.models.mrp.suggestion import MrpSuggestion
from app.schemas.common import PageResult, ResponseModel
from app.schemas.mrp.schemas import BatchReviewRequest, SuggestionOut

suggestions_router = APIRouter()


async def _resolve_run_id(db: AsyncSession, run_id: Optional[int]) -> int:
    if run_id is not None:
        return run_id
    latest = (
        await db.execute(select(func.max(MrpRun.id)).where(MrpRun.status == "success"))
    ).scalar()
    if latest is None:
        raise HTTPException(status_code=404, detail="暂无成功的运算批次")
    return int(latest)


@suggestions_router.get("/suggestions", response_model=ResponseModel[PageResult[SuggestionOut]])
async def list_suggestions(
    run_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    bill_type: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    resolved_run_id = await _resolve_run_id(db, run_id)
    query = select(MrpSuggestion).where(MrpSuggestion.run_id == resolved_run_id)
    count_query = select(func.count()).select_from(MrpSuggestion).where(MrpSuggestion.run_id == resolved_run_id)
    if status:
        query = query.where(MrpSuggestion.status == status)
        count_query = count_query.where(MrpSuggestion.status == status)
    if bill_type:
        query = query.where(MrpSuggestion.bill_type == bill_type)
        count_query = count_query.where(MrpSuggestion.bill_type == bill_type)
    if keyword:
        like = f"%{keyword}%"
        condition = MrpSuggestion.material_code.ilike(like) | MrpSuggestion.material_name.ilike(like)
        query = query.where(condition)
        count_query = count_query.where(condition)
    total = (await db.execute(count_query)).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(MrpSuggestion.bill_type, MrpSuggestion.need_date, MrpSuggestion.material_code)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return ResponseModel(
        data=PageResult(
            total=int(total), page=page, page_size=page_size,
            items=[SuggestionOut.model_validate(r) for r in rows],
        )
    )


@suggestions_router.post("/suggestions/batch-review", response_model=ResponseModel[dict])
async def batch_review(
    payload: BatchReviewRequest,
    current_user: dict = Depends(PermissionChecker("materials.mrp", "review")),
    db: AsyncSession = Depends(get_db),
):
    target_status = "approved" if payload.action == "approve" else "rejected"
    reviewer = current_user.get("username")
    rows = (
        await db.execute(
            select(MrpSuggestion).where(
                MrpSuggestion.id.in_(payload.suggestion_ids),
                MrpSuggestion.status == "pending",
            )
        )
    ).scalars().all()
    for row in rows:
        row.status = target_status
        row.reviewed_by = reviewer
        row.reviewed_at = datetime.now()
    return ResponseModel(data={"updated": len(rows), "status": target_status})
