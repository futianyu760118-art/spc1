from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.production.weekly_capacity_service import (
    build_weekly_capacity,
    generate_weekly_snapshot,
    get_weekly_snapshot,
    list_weekly_recipient_candidates,
    list_weekly_recipient_options,
    list_weekly_recipients,
    list_weekly_snapshots,
    publish_weekly_snapshot,
    push_weekly_capacity,
    update_weekly_recipients,
)

router = APIRouter()


class WeeklyRecipientItem(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    enabled: Optional[bool] = None
    category: Optional[str] = None
    remark: Optional[str] = None


class WeeklyRecipientUpdate(BaseModel):
    items: list[WeeklyRecipientItem]


def _operator_id(current_user: dict) -> int:
    return int(current_user.get("user_id") or current_user["sub"])


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


@router.get("/recipients", response_model=ResponseModel[list[dict]])
async def get_weekly_recipients(
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    items = await list_weekly_recipients(db)
    return ResponseModel(data=items)


@router.get("/recipient-options", response_model=ResponseModel[dict])
async def get_weekly_recipient_options(
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    data = await list_weekly_recipient_options(db)
    return ResponseModel(data=data)


@router.get("/recipient-candidates", response_model=ResponseModel[list[dict]])
async def get_weekly_recipient_candidates(
    keyword: Optional[str] = Query(None),
    org_id: Optional[int] = Query(None),
    role_code: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    items = await list_weekly_recipient_candidates(
        db,
        keyword=keyword,
        org_id=org_id,
        role_code=role_code,
        limit=limit,
    )
    return ResponseModel(data=items)


@router.put("/recipients", response_model=ResponseModel[list[dict]])
async def save_weekly_recipients(
    payload: WeeklyRecipientUpdate,
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    items = await update_weekly_recipients(
        db,
        items=[item.model_dump() for item in payload.items],
        operator=current_user.get("username"),
    )
    return ResponseModel(data=items)


@router.post("/snapshots", response_model=ResponseModel[dict])
async def create_weekly_snapshot(
    week_start: Optional[date] = Query(None),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await generate_weekly_snapshot(
            db,
            week_start=week_start,
            operator=current_user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ResponseModel(data=data)


@router.get("/snapshots", response_model=ResponseModel[list[dict]])
async def get_weekly_snapshots(
    week_start: Optional[date] = Query(None),
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "read")
    ),
    db: AsyncSession = Depends(get_db),
):
    items = await list_weekly_snapshots(db, week_start=week_start)
    return ResponseModel(data=items)


@router.get("/snapshots/{snapshot_id}", response_model=ResponseModel[dict])
async def get_weekly_snapshot_detail(
    snapshot_id: int,
    current_user: dict = Depends(
        PermissionChecker(
            "production.weekly_capacity",
            "read",
            any_of=[("production.monthly_capacity_plan", "read")],
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await get_weekly_snapshot(db, snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ResponseModel(data=data)


@router.post("/snapshots/{snapshot_id}/publish", response_model=ResponseModel[dict])
async def publish_weekly_snapshot_api(
    snapshot_id: int,
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await publish_weekly_snapshot(
            db,
            snapshot_id=snapshot_id,
            operator_id=_operator_id(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ResponseModel(data=data)


@router.post("/push", response_model=ResponseModel[dict])
async def push_next_week_capacity(
    current_user: dict = Depends(
        PermissionChecker("production.monthly_capacity_plan", "manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    """兼容旧入口：生成快照并立即推送企业微信。"""
    operator_id = _operator_id(current_user)
    try:
        data = await push_weekly_capacity(db, operator_id=operator_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ResponseModel(data=data)
