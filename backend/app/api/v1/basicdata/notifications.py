"""通用通知 API — 当前用户的消息中心"""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.basicdata.announcement import Notification
from app.schemas.common import ResponseModel
from pydantic import BaseModel

router = APIRouter()


class CreateNotificationRequest(BaseModel):
    title: str
    content: str
    type: str = "system"
    priority: str = "normal"


def _get_user_id(current_user: dict) -> int:
    return int(current_user["sub"])


# ---------- 创建通知 ----------
@router.post("", response_model=ResponseModel)
async def create_notification(
    request: CreateNotificationRequest,
    current_user: dict = Depends(PermissionChecker("topbar.notifications", "read")),
    db: AsyncSession = Depends(get_db),
):
    uid = _get_user_id(current_user)
    notification = Notification(
        user_id=uid,
        title=request.title,
        content=request.content,
        type=request.type,
        priority=request.priority,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return ResponseModel(data={"id": notification.id})


# ---------- 通知列表 ----------
@router.get("", response_model=ResponseModel)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    is_read: Optional[bool] = None,
    current_user: dict = Depends(PermissionChecker("topbar.notifications", "read")),
    db: AsyncSession = Depends(get_db),
):
    uid = _get_user_id(current_user)
    base = [Notification.user_id == uid]
    if type:
        base.append(Notification.type == type)
    if is_read is not None:
        base.append(Notification.is_read == is_read)

    total = (await db.execute(select(func.count(Notification.id)).where(and_(*base)))).scalar() or 0

    q = (
        select(Notification)
        .where(and_(*base))
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()

    return ResponseModel(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "type": r.type,
                "title": r.title,
                "content": r.content,
                "ref_type": r.ref_type,
                "ref_id": r.ref_id,
                "priority": r.priority,
                "is_read": r.is_read,
                "read_at": r.read_at.strftime("%Y-%m-%d %H:%M") if r.read_at else None,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else None,
            }
            for r in rows
        ],
    })


# ---------- 未读数量（按类型分组） ----------
@router.get("/unread-count", response_model=ResponseModel)
async def unread_count(
    current_user: dict = Depends(PermissionChecker("topbar.notifications", "read")),
    db: AsyncSession = Depends(get_db),
):
    uid = _get_user_id(current_user)
    q = (
        select(Notification.type, func.count(Notification.id))
        .where(and_(Notification.user_id == uid, Notification.is_read == False))  # noqa: E712
        .group_by(Notification.type)
    )
    rows = (await db.execute(q)).all()
    counts = {r[0]: r[1] for r in rows}
    total = sum(counts.values())
    return ResponseModel(data={"total": total, "by_type": counts})


# ---------- 标记单条已读 ----------
@router.post("/{notif_id}/read", response_model=ResponseModel)
async def mark_read(
    notif_id: int,
    current_user: dict = Depends(PermissionChecker("topbar.notifications", "read")),
    db: AsyncSession = Depends(get_db),
):
    uid = _get_user_id(current_user)
    result = await db.execute(
        select(Notification).where(and_(Notification.id == notif_id, Notification.user_id == uid))
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="通知不存在")
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.utcnow()
        await db.commit()
    return ResponseModel(data={"id": notif_id})


# ---------- 全部已读 ----------
@router.post("/read-all", response_model=ResponseModel)
async def mark_all_read(
    type: Optional[str] = None,
    current_user: dict = Depends(PermissionChecker("topbar.notifications", "read")),
    db: AsyncSession = Depends(get_db),
):
    uid = _get_user_id(current_user)
    conditions = [Notification.user_id == uid, Notification.is_read == False]  # noqa: E712
    if type:
        conditions.append(Notification.type == type)
    now = datetime.utcnow()
    await db.execute(
        update(Notification)
        .where(and_(*conditions))
        .values(is_read=True, read_at=now)
    )
    await db.commit()
    return ResponseModel(data={"ok": True})
