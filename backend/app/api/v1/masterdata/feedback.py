"""问题反馈 API

- 任意登录用户可提交反馈
- 普通用户仅能查看/编辑自己的反馈
- admin 可查看全部、回复、删除
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.masterdata.feedback import Feedback
from app.schemas.common import ResponseModel
from app.schemas.masterdata.feedback import (
    FeedbackCreate,
    FeedbackListOut,
    FeedbackOut,
    FeedbackReply,
    FeedbackStatusUpdate,
    FeedbackUpdate,
)
from app.services.common.file_service import FileService

router = APIRouter()


def _is_admin(user: dict) -> bool:
    return (user or {}).get("role") == "admin"


def _has_perm(user: dict, action: str) -> bool:
    """是否有 masterdata.feedback 资源的指定动作权限（admin 自动通过）"""
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    perms = user.get("permissions") or {}
    if not isinstance(perms, dict):
        return False
    actions = perms.get("masterdata.feedback") or []
    return action in actions


def _to_dicts(attachments) -> list[dict]:
    if not attachments:
        return []
    out = []
    for a in attachments:
        if isinstance(a, dict):
            out.append(a)
        elif hasattr(a, "model_dump"):
            out.append(a.model_dump())
    return out


# ---------- 列表 ----------
@router.get("", response_model=ResponseModel[dict])
async def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conds = []
    if not _has_perm(current_user, "update"):
        conds.append(Feedback.submitter_id == current_user.get("user_id"))
    if type:
        conds.append(Feedback.type == type)
    if severity:
        conds.append(Feedback.severity == severity)
    if status:
        conds.append(Feedback.status == status)
    if keyword:
        like = f"%{keyword}%"
        conds.append(or_(
            Feedback.title.ilike(like),
            Feedback.page_path.ilike(like),
            Feedback.submitter_name.ilike(like),
            Feedback.replied_by.ilike(like),
        ))

    base = select(Feedback).where(and_(*conds)) if conds else select(Feedback)
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0

    rows = (await db.execute(
        base.order_by(Feedback.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    # 统计卡
    stat_q = select(Feedback.status, func.count()).group_by(Feedback.status)
    if not _has_perm(current_user, "update"):
        stat_q = stat_q.where(Feedback.submitter_id == current_user.get("user_id"))
    stat_rows = (await db.execute(stat_q)).all()
    by_status = {s: int(c) for s, c in stat_rows}
    stats = {
        "total": int(total),
        "pending": by_status.get("pending", 0),
        "processing": by_status.get("processing", 0),
        "resolved": by_status.get("resolved", 0),
        "closed": by_status.get("closed", 0),
    }

    return ResponseModel(data={
        "items": [FeedbackOut.model_validate(r).model_dump() for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "stats": stats,
    })


# ---------- 详情 ----------
@router.get("/{feedback_id}", response_model=ResponseModel[FeedbackOut])
async def get_feedback(
    feedback_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if not _has_perm(current_user, "update") and fb.submitter_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="无权查看")
    return ResponseModel(data=FeedbackOut.model_validate(fb))


# ---------- 创建 ----------
@router.post("", response_model=ResponseModel[FeedbackOut])
async def create_feedback(
    body: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    attachments = _to_dicts(body.attachments)
    fb = Feedback(
        type=body.type or "issue",
        severity=body.severity or "low",
        page_path=body.page_path,
        title=body.title,
        description=body.description,
        attachments=attachments or None,
        status="pending",
        submitter_id=int(current_user.get("user_id")),
        submitter_name=current_user.get("username") or "",
    )
    db.add(fb)
    await db.flush()

    # 关联文件资产
    if attachments:
        svc = FileService(db)
        await svc.attach([a.get("key") for a in attachments], "feedback", str(fb.id))

    await db.commit()
    await db.refresh(fb)
    return ResponseModel(data=FeedbackOut.model_validate(fb))


# ---------- 提交人更新（仅 pending） ----------
@router.put("/{feedback_id}", response_model=ResponseModel[FeedbackOut])
async def update_feedback(
    feedback_id: int,
    body: FeedbackUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")

    can_handle = _has_perm(current_user, "update")
    if not can_handle:
        if fb.submitter_id != current_user.get("user_id"):
            raise HTTPException(status_code=403, detail="无权编辑")
        if fb.status != "pending":
            raise HTTPException(status_code=400, detail="已处理的反馈不能修改")

    old_keys = {a.get("key") for a in (fb.attachments or []) if isinstance(a, dict) and a.get("key")}

    if body.type is not None:
        fb.type = body.type
    if body.severity is not None:
        fb.severity = body.severity
    if body.page_path is not None:
        fb.page_path = body.page_path
    if body.title is not None:
        fb.title = body.title
    if body.description is not None:
        fb.description = body.description
    if body.attachments is not None:
        new_attachments = _to_dicts(body.attachments)
        new_keys = {a.get("key") for a in new_attachments if a.get("key")}
        fb.attachments = new_attachments or None
        svc = FileService(db)
        to_attach = list(new_keys - old_keys)
        to_detach = list(old_keys - new_keys)
        if to_attach:
            await svc.attach(to_attach, "feedback", str(fb.id))
        if to_detach:
            await svc.detach(to_detach)

    await db.commit()
    await db.refresh(fb)
    return ResponseModel(data=FeedbackOut.model_validate(fb))


# ---------- 管理员回复 ----------
@router.post("/{feedback_id}/reply", response_model=ResponseModel[FeedbackOut])
async def reply_feedback(
    feedback_id: int,
    body: FeedbackReply,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _has_perm(current_user, "update"):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")

    if not body.reply and not body.status:
        raise HTTPException(status_code=400, detail="回复内容和状态至少填一项")

    if body.reply:
        fb.reply = body.reply
        fb.replied_by = current_user.get("username")
        fb.replied_at = datetime.now()
    if body.status:
        fb.status = body.status
    elif body.reply and fb.status == "pending":
        fb.status = "resolved"

    await db.commit()
    await db.refresh(fb)
    return ResponseModel(data=FeedbackOut.model_validate(fb))


# ---------- 状态变更（admin 任意 / 提交人有限） ----------
@router.patch("/{feedback_id}/status", response_model=ResponseModel[FeedbackOut])
async def update_status(
    feedback_id: int,
    body: FeedbackStatusUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed = {"pending", "processing", "resolved", "closed"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail="非法状态")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")

    if _has_perm(current_user, "update"):
        fb.status = body.status
    else:
        # 提交人：仅可在 resolved 后 close，或 closed 后重开为 pending
        if fb.submitter_id != current_user.get("user_id"):
            raise HTTPException(status_code=403, detail="无权变更")
        if body.status == "closed" and fb.status != "resolved":
            raise HTTPException(status_code=400, detail="只有已解决的反馈才能关闭")
        if body.status == "pending" and fb.status != "closed":
            raise HTTPException(status_code=400, detail="只有已关闭的反馈才能重开")
        if body.status not in ("closed", "pending"):
            raise HTTPException(status_code=403, detail="无权变更为该状态")
        fb.status = body.status

    await db.commit()
    await db.refresh(fb)
    return ResponseModel(data=FeedbackOut.model_validate(fb))


# ---------- 删除（管理员） ----------
@router.delete("/{feedback_id}", response_model=ResponseModel[dict])
async def delete_feedback(
    feedback_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _has_perm(current_user, "delete"):
        raise HTTPException(status_code=403, detail="无权删除反馈")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")

    # 解引用附件
    keys = [a.get("key") for a in (fb.attachments or []) if isinstance(a, dict) and a.get("key")]
    if keys:
        svc = FileService(db)
        await svc.detach(keys)

    await db.delete(fb)
    await db.commit()
    return ResponseModel(data={"deleted": feedback_id})
