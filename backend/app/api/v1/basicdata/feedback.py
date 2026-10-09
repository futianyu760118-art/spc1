"""问题反馈 API

- 任意登录用户可提交反馈
- 普通用户仅能查看/编辑自己的反馈
- admin 可查看全部、回复、删除
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import PermissionChecker
from app.models.basicdata.announcement import Notification
from app.models.basicdata.feedback import Feedback
from app.schemas.common import ResponseModel
from app.schemas.basicdata.feedback import (
    FeedbackAiFinish,
    FeedbackAiProgress,
    FeedbackAiResult,
    FeedbackAiResultFile,
    FeedbackAiResultGate,
    FeedbackCreate,
    FeedbackListOut,
    FeedbackOut,
    FeedbackReply,
    FeedbackStatusUpdate,
    FeedbackUpdate,
)
from app.services.common.file_service import FileService
from app.services.notification.notification_broker import publish_unread_update

logger = logging.getLogger(__name__)

_FEEDBACK_TYPE_LABELS = {"issue": "问题", "suggestion": "建议", "inquiry": "咨询"}
_SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
_STATUS_LABELS = {"pending": "待处理", "processing": "处理中", "resolved": "已解决", "closed": "已关闭"}
_NOTIFICATION_TITLE_MAX = 256
_NOTIFICATION_CONTENT_MAX = 512

router = APIRouter()


def _clip_notification_text(text: str, limit: int) -> str:
    """通知表 title/content 为 varchar(256/512)，超长写入会触发 500，统一截断。"""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _is_admin(user: dict) -> bool:
    return (user or {}).get("role") == "admin"


def _has_perm(user: dict, action: str) -> bool:
    """是否有 basicdata.feedback 资源的指定动作权限（admin 自动通过）"""
    if not user:
        return False
    if _is_admin(user):
        return True
    perms = user.get("permissions") or {}
    if not isinstance(perms, dict):
        return False

    resources = ("basicdata.feedback", "masterdata.feedback")
    for resource in resources:
        actions = perms.get(resource) or []
        if isinstance(actions, list) and action in actions:
            return True

    for resource in resources:
        parent = resource.split(".", 1)[0]
        actions = perms.get(parent) or []
        if isinstance(actions, list) and action in actions:
            return True
    return False


def _can_handle(user: dict) -> bool:
    """是否有「处理问题反馈」权限（admin 自动通过）。

    优先判新权限 basicdata.feedback.handle 的 handle 动作；
    兼容旧权限：basicdata.feedback 的 update 动作（避免自定义角色误伤）。
    """
    if not user:
        return False
    if _is_admin(user):
        return True
    perms = user.get("permissions") or {}
    if not isinstance(perms, dict):
        return False
    for resource in ("basicdata.feedback.handle", "masterdata.feedback.handle"):
        actions = perms.get(resource) or []
        if isinstance(actions, list) and "handle" in actions:
            return True
    return _has_perm(user, "update")


def _get_user_id(user: dict) -> int:
    return int(user.get("user_id") or user["sub"])


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


async def _insert_handler_notifications(db: AsyncSession, fb: Feedback) -> list[int]:
    """向所有「有反馈处理权限」的活跃用户插入 feedback_alert 通知行，返回被通知的 user_id 列表。

    处理人按权限判定（镜像 _has_perm 'update'），不硬编码角色名：
    - admin 自动通过；
    - 其余角色在 sys_role.permissions JSONB 合并 ROLE_PERMISSION_ADDITIONS 后，
      含 basicdata.feedback / masterdata.feedback / 父级 basicdata 的 update 动作即视为处理人。
    这样在 RoleManagement 调整权限矩阵后，通知接收人自动跟随。
    严重度 high → priority important（触发加载时 toast），其余 normal。排除提交人本人。
    """
    from app.core.permissions import merge_role_permission_additions
    rows = await db.execute(text("""
        SELECT u.id, r.role_code, r.permissions
        FROM sys_user u
        JOIN sys_role r ON u.role_id = r.id
        WHERE u.is_active = TRUE
    """))
    handler_ids: list[int] = []
    for uid, role_code, raw_perms in rows:
        if uid is None:
            continue
        perms = merge_role_permission_additions(
            role_code, raw_perms if isinstance(raw_perms, dict) else {}
        )
        if _can_handle({"role": role_code, "permissions": perms}):
            handler_ids.append(int(uid))
    if fb.submitter_id and fb.submitter_id in handler_ids:
        handler_ids = [u for u in handler_ids if u != fb.submitter_id]
    if not handler_ids:
        return []

    priority = "important" if fb.severity == "high" else "normal"
    title = f"[问题反馈]{fb.title}"
    content = fb.description or ""

    for hid in handler_ids:
        db.add(Notification(
            user_id=hid,
            type="feedback",
            title=_clip_notification_text(title, _NOTIFICATION_TITLE_MAX),
            content=_clip_notification_text(content, _NOTIFICATION_CONTENT_MAX),
            ref_type="feedback",
            ref_id=fb.id,
            sender_id=fb.submitter_id,
            sender_name=fb.submitter_name,
            priority=priority,
            is_read=False,
        ))
    await db.flush()
    return handler_ids


async def _insert_submitter_progress_notification(
    db: AsyncSession, fb: Feedback, actor_user: dict, action_desc: str
) -> Optional[int]:
    """处理进度变化时通知提交人;提交人=操作人本人时跳过。返回提交人 user_id 或 None。"""
    if not fb.submitter_id:
        return None
    if int(fb.submitter_id) == _get_user_id(actor_user):
        return None
    priority = "important" if fb.severity == "high" else "normal"
    db.add(Notification(
        user_id=fb.submitter_id,
        type="feedback",
        title=_clip_notification_text(
            f"[问题反馈]您的反馈「{fb.title}」处理进度有更新", _NOTIFICATION_TITLE_MAX
        ),
        content=_clip_notification_text(action_desc, _NOTIFICATION_CONTENT_MAX),
        ref_type="feedback",
        ref_id=fb.id,
        sender_id=_get_user_id(actor_user),
        sender_name=actor_user.get("username"),
        priority=priority,
        is_read=False,
    ))
    await db.flush()
    return fb.submitter_id


# ---------- AI 派单等待（长轮询） ----------
_AI_QUEUE_WAIT_DEFAULT_SECONDS = 20
_AI_QUEUE_WAIT_MAX_IDS = 10
_AI_QUEUE_WAIT_RECHECK_SECONDS = 1.0
_queue_waiters: set[asyncio.Event] = set()


def notify_queue_waiters() -> None:
    """派单提交后唤醒所有等待中的长轮询请求（毫秒级送达 runner）。"""
    for waiter in list(_queue_waiters):
        waiter.set()


async def _list_queued_ids(db: AsyncSession, limit: int) -> list[int]:
    rows = (await db.execute(
        select(Feedback.id)
        .where(Feedback.ai_status == "queued")
        .order_by(Feedback.created_at.asc())
        .limit(limit)
    )).scalars().all()
    return [int(row) for row in rows]


# ---------- 列表 ----------
@router.get("", response_model=ResponseModel[dict])
async def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    ai_status: Optional[str] = Query(None, description="AI 实现状态筛选，逗号分隔"),
    keyword: Optional[str] = None,
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query(None, description="排序方向 asc/desc"),
    submitter_name: Optional[str] = Query(None, description="提交人筛选，逗号分隔"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    SORTABLE = {
        'title': Feedback.title,
        'type': Feedback.type,
        'severity': Feedback.severity,
        'status': Feedback.status,
        'page_path': Feedback.page_path,
        'submitter_name': Feedback.submitter_name,
        'created_at': Feedback.created_at,
        'replied_by': Feedback.replied_by,
    }

    conds = []
    if not _can_handle(current_user):
        conds.append(Feedback.submitter_id == current_user.get("user_id"))
    if type:
        types = [t.strip() for t in type.split(",") if t.strip()]
        if types:
            conds.append(Feedback.type.in_(types))
    if severity:
        severities = [s.strip() for s in severity.split(",") if s.strip()]
        if severities:
            conds.append(Feedback.severity.in_(severities))
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            conds.append(Feedback.status.in_(statuses))
    if ai_status:
        ai_statuses = [s.strip() for s in ai_status.split(",") if s.strip()]
        if ai_statuses:
            conds.append(Feedback.ai_status.in_(ai_statuses))
    if keyword:
        like = f"%{keyword}%"
        conds.append(or_(
            Feedback.title.ilike(like),
            Feedback.page_path.ilike(like),
            Feedback.submitter_name.ilike(like),
            Feedback.replied_by.ilike(like),
        ))
    if submitter_name:
        submitters = [s.strip() for s in submitter_name.split(",") if s.strip()]
        if submitters:
            conds.append(Feedback.submitter_name.in_(submitters))

    base = select(Feedback).where(and_(*conds)) if conds else select(Feedback)
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0

    # 排序
    order_clauses = []
    if sort_by and sort_by in SORTABLE:
        col = SORTABLE[sort_by]
        if sort_order == 'desc':
            order_clauses.append(col.desc().nullslast())
        else:
            order_clauses.append(col.asc().nullslast())
    if not order_clauses:
        order_clauses = [Feedback.created_at.desc()]

    rows = (await db.execute(
        base.order_by(*order_clauses)
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    # 统计卡
    stat_q = select(Feedback.status, func.count()).group_by(Feedback.status)
    if not _can_handle(current_user):
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


@router.get("/ai-queue-wait", response_model=ResponseModel[dict])
async def ai_queue_wait(
    timeout_seconds: float = Query(_AI_QUEUE_WAIT_DEFAULT_SECONDS, ge=1, le=30),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """长轮询等待待派反馈：有任务立即返回，无任务挂起至多 timeout_seconds。

    注意：本路由必须声明在 `GET /{feedback_id}` 之前，否则会被 int 路径参数吞掉。
    """
    if not _can_handle(current_user):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    waiter = asyncio.Event()
    _queue_waiters.add(waiter)
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            ids = await _list_queued_ids(db, _AI_QUEUE_WAIT_MAX_IDS)
            await db.rollback()  # 只读事务结束，长轮询不占用连接
            if ids:
                return ResponseModel(data={"ids": ids})
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ResponseModel(data={"ids": []})
            try:
                await asyncio.wait_for(
                    waiter.wait(),
                    timeout=min(_AI_QUEUE_WAIT_RECHECK_SECONDS, remaining),
                )
            except asyncio.TimeoutError:
                pass
            waiter.clear()
    finally:
        _queue_waiters.discard(waiter)


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
    if not _can_handle(current_user) and fb.submitter_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="无权查看")
    return ResponseModel(data=FeedbackOut.model_validate(fb))


# ---------- 创建 ----------
@router.post("", response_model=ResponseModel[FeedbackOut])
async def create_feedback(
    body: FeedbackCreate,
    current_user: dict = Depends(PermissionChecker("topbar.feedback", "read")),
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
        submitter_id=_get_user_id(current_user),
        submitter_name=current_user.get("username") or "",
    )
    db.add(fb)
    await db.flush()

    # 关联文件资产
    if attachments:
        svc = FileService(db)
        await svc.attach([a.get("key") for a in attachments], "feedback", str(fb.id))

    # 通知处理人（插 notification 行；失败只记日志，不影响反馈提交）
    handler_ids: list[int] = []
    try:
        handler_ids = await _insert_handler_notifications(db, fb)
    except Exception as e:
        logger.warning(f"[feedback] 插入处理人通知失败 feedback_id={fb.id}: {e}")

    await db.commit()
    await db.refresh(fb)

    # commit 后 SSE 推送未读计数（计数反映已提交数据；Redis 失败静默丢弃）
    if handler_ids:
        try:
            for hid in handler_ids:
                await publish_unread_update(db, hid)
        except Exception as e:
            logger.warning(f"[feedback] SSE 推送失败 feedback_id={fb.id}: {e}")

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

    can_handle = _can_handle(current_user)
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
    if not _can_handle(current_user):
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

    # 通知提交人处理进度(失败只记日志,不影响回复)
    notified_uid: Optional[int] = None
    try:
        parts = []
        if body.reply:
            parts.append(f"处理人 {current_user.get('username')} 回复:{body.reply}")
        if body.status:
            parts.append(f"状态更新为「{_STATUS_LABELS.get(body.status, body.status)}」")
        if not parts:
            parts.append("处理进度有更新")
        notified_uid = await _insert_submitter_progress_notification(
            db, fb, current_user, ";".join(parts)
        )
    except Exception as e:
        logger.warning(f"[feedback] 插入提交人进度通知失败 feedback_id={fb.id}: {e}")

    await db.commit()
    await db.refresh(fb)
    if notified_uid:
        try:
            await publish_unread_update(db, notified_uid)
        except Exception as e:
            logger.warning(f"[feedback] SSE 推送失败 feedback_id={fb.id}: {e}")
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

    if _can_handle(current_user):
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

    # 通知提交人处理进度(仅处理人操作时;提交人自己 close/重开不通知)
    notified_uid: Optional[int] = None
    if _can_handle(current_user):
        try:
            notified_uid = await _insert_submitter_progress_notification(
                db, fb, current_user,
                f"处理人 {current_user.get('username')} 将状态更新为「{_STATUS_LABELS.get(body.status, body.status)}」",
            )
        except Exception as e:
            logger.warning(f"[feedback] 插入提交人进度通知失败 feedback_id={fb.id}: {e}")

    await db.commit()
    await db.refresh(fb)
    if notified_uid:
        try:
            await publish_unread_update(db, notified_uid)
        except Exception as e:
            logger.warning(f"[feedback] SSE 推送失败 feedback_id={fb.id}: {e}")
    return ResponseModel(data=FeedbackOut.model_validate(fb))


# ---------- AI 自动实现（派单 / 认领 / 回写） ----------
_AI_TERMINAL_STATUSES = ("resolved", "closed")
_AI_STAGE_LABELS = {
    "preparing": "准备隔离环境",
    "fetching": "下载附件",
    "agent": "AI 修改代码",
    "gate_backend": "后端测试",
    "gate_frontend": "前端构建",
    "committing": "提交代码",
}
_AI_PROGRESS_MAX_ENTRIES = 50
_AI_PROGRESS_MAX_ACTIONS_PER_POST = 20
_AI_PROGRESS_ACTION_MAX_LEN = 200
_AI_RESULT_MAX_FILES = 200
_AI_RESULT_MAX_GATES = 4
_AI_RESULT_MAX_PATH_LEN = 300
_AI_RESULT_MAX_OUTPUT_TAIL = 4000
_AI_RESULT_MAX_SUMMARY = 1500
_AI_RESULT_MAX_ERROR = 2000
_AI_RESULT_MAX_BYTES = 64 * 1024


def _clamp_ai_result(result: FeedbackAiResult) -> Optional[dict]:
    """钳制 runner 回写的结构化结果（只钳制不拒绝，避免回写 422 卡死反馈）；整体超限返回 None 退化为 ai_note 展示。"""
    clamped = FeedbackAiResult(
        branch=(result.branch or "")[:128] or None,
        summary=(result.summary or "")[:_AI_RESULT_MAX_SUMMARY] or None,
        runDir=(result.runDir or "")[:_AI_RESULT_MAX_PATH_LEN] or None,
        error=(result.error or "")[:_AI_RESULT_MAX_ERROR] or None,
        files=[
            FeedbackAiResultFile(
                path=(f.path or "")[:_AI_RESULT_MAX_PATH_LEN],
                status=((f.status or "M").strip().upper()[:1] or "M"),
                additions=max(0, f.additions or 0),
                deletions=max(0, f.deletions or 0),
            )
            for f in (result.files or [])[:_AI_RESULT_MAX_FILES]
        ] or None,
        gates=[
            FeedbackAiResultGate(
                name=(g.name or "")[:32],
                passed=bool(g.passed),
                exitCode=g.exitCode,
                durationSeconds=g.durationSeconds,
                outputTail=(g.outputTail or "")[:_AI_RESULT_MAX_OUTPUT_TAIL] or None,
            )
            for g in (result.gates or [])[:_AI_RESULT_MAX_GATES]
        ] or None,
    )
    dumped = clamped.model_dump()
    if len(json.dumps(dumped, ensure_ascii=False).encode("utf-8")) > _AI_RESULT_MAX_BYTES:
        logger.warning("[feedback] ai_result 超过 %d 字节，已丢弃（界面退化为 ai_note 展示）", _AI_RESULT_MAX_BYTES)
        return None
    return dumped


@router.post("/{feedback_id}/ai-queue", response_model=ResponseModel[FeedbackOut])
async def ai_queue_feedback(
    feedback_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """处理人派单：none/failed/running → queued；已解决/已关闭不允许派单。"""
    if not _can_handle(current_user):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id).with_for_update()
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if fb.status in _AI_TERMINAL_STATUSES:
        raise HTTPException(status_code=400, detail="已解决/已关闭的反馈不能派单")
    if fb.ai_status == "queued":
        raise HTTPException(status_code=400, detail="该反馈已在 AI 排队中")
    if fb.ai_status == "done":
        raise HTTPException(status_code=400, detail="该反馈已由 AI 实现，如需重做请先清理分支")

    fb.ai_status = "queued"
    fb.ai_progress = None
    fb.ai_stage = None
    fb.ai_stage_started_at = None
    fb.ai_result = None
    fb.ai_requested_by = current_user.get("username")
    fb.ai_requested_at = datetime.now()
    if fb.status == "pending":
        fb.status = "processing"

    await db.commit()
    await db.refresh(fb)
    notify_queue_waiters()
    return ResponseModel(data=FeedbackOut.model_validate(fb))


@router.post("/{feedback_id}/ai-cancel", response_model=ResponseModel[FeedbackOut])
async def ai_cancel_feedback(
    feedback_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """处理人撤回排队：仅 queued → none。"""
    if not _can_handle(current_user):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id).with_for_update()
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if fb.ai_status != "queued":
        raise HTTPException(status_code=400, detail="仅排队中的反馈可取消")

    fb.ai_status = "none"
    await db.commit()
    await db.refresh(fb)
    return ResponseModel(data=FeedbackOut.model_validate(fb))


@router.post("/{feedback_id}/ai-claim", response_model=ResponseModel[FeedbackOut])
async def ai_claim_feedback(
    feedback_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Runner 原子认领：仅 queued → running；已被认领返回 409。"""
    if not _can_handle(current_user):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id).with_for_update()
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if fb.ai_status != "queued":
        raise HTTPException(status_code=409, detail=f"反馈当前状态为 {fb.ai_status}，无法认领")

    fb.ai_status = "running"
    await db.commit()
    await db.refresh(fb)
    return ResponseModel(data=FeedbackOut.model_validate(fb))


@router.post("/{feedback_id}/ai-progress", response_model=ResponseModel[dict])
async def ai_progress_feedback(
    feedback_id: int,
    body: FeedbackAiProgress,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Runner 上报执行进度：仅 running 接受；stage 白名单；动作截断并裁剪历史。"""
    if not _can_handle(current_user):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id).with_for_update()
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if fb.ai_status != "running":
        raise HTTPException(status_code=409, detail=f"反馈当前状态为 {fb.ai_status}，拒绝上报进度")

    actions: list[str] = []
    for raw in body.actions or []:
        text = (raw or "").strip()
        if not text:
            continue
        actions.append(text[:_AI_PROGRESS_ACTION_MAX_LEN])
        if len(actions) >= _AI_PROGRESS_MAX_ACTIONS_PER_POST:
            break
    if not body.stage and not actions:
        raise HTTPException(status_code=400, detail="stage 和 actions 至少填一项")
    if body.stage and body.stage not in _AI_STAGE_LABELS:
        raise HTTPException(status_code=400, detail=f"非法阶段: {body.stage}")

    entries = list(fb.ai_progress or [])
    now_iso = datetime.now().isoformat(timespec="seconds")
    if body.stage:
        fb.ai_stage = body.stage
        fb.ai_stage_started_at = datetime.now()
        entries.append({
            "at": now_iso,
            "kind": "stage",
            "stage": body.stage,
            "text": _AI_STAGE_LABELS[body.stage],
        })
    for text in actions:
        entries.append({"at": now_iso, "kind": "action", "stage": fb.ai_stage, "text": text})
    fb.ai_progress = entries[-_AI_PROGRESS_MAX_ENTRIES:]

    await db.commit()
    await db.refresh(fb)
    return ResponseModel(data={"ai_status": fb.ai_status, "ai_stage": fb.ai_stage})


@router.post("/{feedback_id}/ai-finish", response_model=ResponseModel[FeedbackOut])
async def ai_finish_feedback(
    feedback_id: int,
    body: FeedbackAiFinish,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Runner 回写实现结果：仅 running 可写入；自动回复并通知提交人。"""
    if not _can_handle(current_user):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id).with_for_update()
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if fb.ai_status != "running":
        raise HTTPException(status_code=409, detail=f"反馈当前状态为 {fb.ai_status}，拒绝回写")

    if body.success:
        fb.ai_status = "done"
        fb.ai_branch = body.branch
        fb.ai_note = body.summary
        reply_text = (
            f"【AI 自动实现待审核】分支：{body.branch or '—'}。\n"
            f"验证说明：{body.summary or '已通过自动门禁'}。\n"
            "请在开发机审核 diff 并合入后再更新本反馈状态。"
        )
    else:
        fb.ai_status = "failed"
        fb.ai_note = body.error
        reply_text = f"【AI 自动实现失败】{body.error or '未知原因'}。修改反馈后可点击「重试」。"

    fb.ai_result = _clamp_ai_result(body.result) if body.result else None
    fb.ai_stage = None
    fb.ai_stage_started_at = None
    fb.reply = reply_text
    fb.replied_by = "AI Runner"
    fb.replied_at = datetime.now()

    notified_uid: Optional[int] = None
    try:
        notified_uid = await _insert_submitter_progress_notification(db, fb, current_user, reply_text)
    except Exception as e:
        logger.warning(f"[feedback] AI 结果通知提交人失败 feedback_id={fb.id}: {e}")

    await db.commit()
    await db.refresh(fb)
    if notified_uid:
        try:
            await publish_unread_update(db, notified_uid)
        except Exception as e:
            logger.warning(f"[feedback] SSE 推送失败 feedback_id={fb.id}: {e}")
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
