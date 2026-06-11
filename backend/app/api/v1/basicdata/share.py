"""基础数据与集成中心 — 页面分享链接 API"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker, create_share_access_token
from app.models.basicdata.share_link import ShareLink
from app.schemas.common import ResponseModel

router = APIRouter()


# ── Schemas ──

class ShareCreateRequest(BaseModel):
    target_path: str
    target_params: Optional[dict] = None
    expires_in: Optional[str] = "30d"  # "7d" | "30d" | "90d" | "permanent"
    permissions: Optional[list[str]] = ["read"]  # ["read","create","update","delete"]


class ShareVerifyResponse(BaseModel):
    access_token: str
    target_path: str
    target_params: Optional[dict] = None
    permissions: Optional[list[str]] = None


class ShareListItem(BaseModel):
    id: int
    token: str
    target_path: str
    target_params: Optional[dict] = None
    permissions: Optional[list[str]] = None
    expires_at: Optional[datetime] = None
    is_revoked: bool
    access_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ──

_EXPIRES_MAP = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "permanent": None,
}


def _generate_token() -> str:
    return secrets.token_urlsafe(24)


def _get_user_id(current_user: dict) -> int:
    return int(current_user.get("user_id") or current_user["sub"])


# ── Endpoints ──

@router.post("", response_model=ResponseModel[dict])
async def create_share_link(
    body: ShareCreateRequest,
    current_user: dict = Depends(PermissionChecker("topbar.share", "read")),
    db: AsyncSession = Depends(get_db),
):
    """创建分享链接（需登录）"""
    delta = _EXPIRES_MAP.get(body.expires_in, timedelta(days=30))
    expires_at = datetime.now(timezone.utc) + delta if delta else None

    token = _generate_token()
    share = ShareLink(
        token=token,
        target_path=body.target_path,
        target_params=body.target_params,
        permissions=body.permissions,
        created_by=_get_user_id(current_user),
        expires_at=expires_at,
    )
    db.add(share)
    await db.flush()

    return ResponseModel(data={
        "id": share.id,
        "token": token,
        "share_url": f"/share/{token}",
        "expires_at": expires_at.isoformat() if expires_at else None,
    })


@router.get("/list", response_model=ResponseModel[list[ShareListItem]])
async def list_share_links(
    current_user: dict = Depends(PermissionChecker("topbar.share", "read")),
    db: AsyncSession = Depends(get_db),
):
    """查询我创建的分享链接（需登录）"""
    result = await db.execute(
        select(ShareLink)
        .where(ShareLink.created_by == _get_user_id(current_user))
        .order_by(ShareLink.created_at.desc())
    )
    items = result.scalars().all()
    return ResponseModel(data=[ShareListItem.model_validate(item) for item in items])


@router.get("/{token}", response_model=ResponseModel[ShareVerifyResponse])
async def verify_share_link(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """验证分享链接，签发临时 JWT（无需登录）"""
    result = await db.execute(
        select(ShareLink).where(ShareLink.token == token)
    )
    share = result.scalar_one_or_none()

    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享链接不存在")

    if share.is_revoked:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="分享链接已被撤销")

    if share.expires_at and share.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="分享链接已过期")

    # 增加访问计数
    await db.execute(
        update(ShareLink)
        .where(ShareLink.id == share.id)
        .values(access_count=ShareLink.access_count + 1)
    )
    await db.flush()

    # 签发临时 JWT，标记为分享访问
    share_permissions = share.permissions or ["read"]
    access_token = create_share_access_token(data={
        "sub": str(share.created_by),
        "share_target_path": share.target_path,
        "share_token": share.token,
        "share_permissions": share_permissions,
    })

    return ResponseModel(data=ShareVerifyResponse(
        access_token=access_token,
        target_path=share.target_path,
        target_params=share.target_params,
        permissions=share_permissions,
    ))


@router.delete("/{share_id}", response_model=ResponseModel[dict])
async def revoke_share_link(
    share_id: int,
    current_user: dict = Depends(PermissionChecker("topbar.share", "read")),
    db: AsyncSession = Depends(get_db),
):
    """撤销分享链接（仅创建者可操作）"""
    result = await db.execute(
        select(ShareLink).where(ShareLink.id == share_id)
    )
    share = result.scalar_one_or_none()

    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享链接不存在")

    if share.created_by != _get_user_id(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能撤销自己创建的分享链接")

    share.is_revoked = True
    await db.flush()

    return ResponseModel(data={"id": share.id, "message": "分享链接已撤销"})
