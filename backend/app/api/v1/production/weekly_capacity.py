from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.production.weekly_capacity_service import (
    build_weekly_capacity,
    push_weekly_capacity,
)

router = APIRouter()


@router.get("/next", response_model=ResponseModel[dict])
async def get_next_week_capacity(
    week_start: Optional[date] = Query(None),
    current_user: dict = Depends(
        PermissionChecker(
            "production.weekly_capacity",
            "read",
            any_of=[("production.monthly_capacity_plan", "read")],
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    """下周产能计划（只读）；week_start 不传默认下一个自然周的周一。"""
    data = await build_weekly_capacity(db, week_start=week_start)
    return ResponseModel(data=data)


@router.post("/push", response_model=ResponseModel[dict])
async def push_next_week_capacity(
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    """生成下周计划只读分享链接并推送企业微信（测试阶段仅陈巧霞）。"""
    operator_id = int(current_user.get("user_id") or current_user["sub"])
    try:
        data = await push_weekly_capacity(db, operator_id=operator_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ResponseModel(data=data)
