"""异常与质量中心 — 异常总池 + 闭环跟踪 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel, PageResult
from app.schemas.exception.schemas import ExceptionPoolItem, ClosureTrackingData
from app.services.exception.exception_pool_service import get_exception_pool, get_closure_tracking

router = APIRouter()


@router.get("", response_model=ResponseModel[PageResult[ExceptionPoolItem]])
async def list_exception_pool(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    source_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("exceptions.pool", "read")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await get_exception_pool(
        db, source_type=source_type, status=status, owner=owner,
        keyword=keyword, page=page, page_size=page_size,
    )
    return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))


@router.get("/closure-tracking", response_model=ResponseModel[ClosureTrackingData])
async def get_closure_tracking_view(
    current_user: dict = Depends(PermissionChecker("exceptions.closure", "read")),
    db: AsyncSession = Depends(get_db),
):
    data = await get_closure_tracking(db)
    return ResponseModel(data=data)
