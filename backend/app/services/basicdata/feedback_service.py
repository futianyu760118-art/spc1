"""问题反馈服务：创建/撤销与处理人通知，路由与智能助手工具共用。"""

import logging
from typing import List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import check_permission
from app.models.basicdata.announcement import Notification
from app.models.basicdata.feedback import Feedback
from app.services.common.file_service import FileService
from app.services.notification.text_utils import (
    NOTIFICATION_CONTENT_MAX,
    NOTIFICATION_TITLE_MAX,
    clip_text,
)

logger = logging.getLogger(__name__)

FEEDBACK_TYPES = ("issue", "suggestion", "inquiry")
FEEDBACK_SEVERITIES = ("low", "medium", "high")
FEEDBACK_TITLE_MAX = 200
FEEDBACK_DESCRIPTION_MAX = 5000


def is_admin(user: dict) -> bool:
    return (user or {}).get("role") == "admin"


def has_feedback_perm(user: dict, action: str) -> bool:
    """是否有 basicdata.feedback 资源的指定动作权限（admin 自动通过）"""
    if not user:
        return False
    if is_admin(user):
        return True
    perms = user.get("permissions") or {}
    return any(
        check_permission(perms, resource, action)
        for resource in ("basicdata.feedback", "masterdata.feedback")
    )


def can_handle(user: dict) -> bool:
    """是否有「处理问题反馈」权限（admin 自动通过）。

    优先判新权限 basicdata.feedback.handle 的 handle 动作；
    兼容旧权限：basicdata.feedback 的 update 动作（避免自定义角色误伤）。
    """
    if not user:
        return False
    if is_admin(user):
        return True
    perms = user.get("permissions") or {}
    if not isinstance(perms, dict):
        return False
    for resource in ("basicdata.feedback.handle", "masterdata.feedback.handle"):
        actions = perms.get(resource) or []
        if isinstance(actions, list) and "handle" in actions:
            return True
    return has_feedback_perm(user, "update")


def get_user_id(user: dict) -> int:
    return int(user.get("user_id") or user["sub"])


def to_dicts(attachments) -> List[dict]:
    if not attachments:
        return []
    out = []
    for a in attachments:
        if isinstance(a, dict):
            out.append(a)
        elif hasattr(a, "model_dump"):
            out.append(a.model_dump())
    return out


async def insert_handler_notifications(db: AsyncSession, fb: Feedback) -> List[int]:
    """向所有「有反馈处理权限」的活跃用户插入 feedback_alert 通知行，返回被通知的 user_id 列表。

    处理人按权限判定（镜像 can_handle 'update'），不硬编码角色名：
    - admin 自动通过；
    - 其余角色在 sys_role.permissions JSONB 合并 ROLE_PERMISSION_ADDITIONS 后，
      含 basicdata.feedback / masterdata.feedback / 父级 basicdata 的 update 动作即视为处理人。
    严重度 high → priority important（触发加载时 toast），其余 normal。排除提交人本人。
    """
    from app.services.common.permission_users import user_ids_matching
    handler_ids = await user_ids_matching(
        db,
        lambda role_code, perms: can_handle({"role": role_code, "permissions": perms}),
    )
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
            title=clip_text(title, NOTIFICATION_TITLE_MAX),
            content=clip_text(content, NOTIFICATION_CONTENT_MAX),
            ref_type="feedback",
            ref_id=fb.id,
            sender_id=fb.submitter_id,
            sender_name=fb.submitter_name,
            priority=priority,
            is_read=False,
        ))
    await db.flush()
    return handler_ids


async def publish_unread_updates(db: AsyncSession, handler_ids: List[int]) -> None:
    """推送处理人未读数（best-effort；Redis/SSE 失败只记日志）。"""
    if not handler_ids:
        return
    from app.services.notification.notification_broker import publish_unread_update
    try:
        for hid in handler_ids:
            await publish_unread_update(db, hid)
    except Exception as e:
        logger.warning(f"[feedback] SSE 推送失败: {e}")


class FeedbackError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class FeedbackValidationError(FeedbackError):
    pass


class FeedbackRevokeError(FeedbackError):
    pass


def _validate_content(title: str, description: str) -> None:
    if not title.strip():
        raise FeedbackValidationError("反馈标题不能为空")
    if not description.strip():
        raise FeedbackValidationError("反馈描述不能为空")
    if len(title) > FEEDBACK_TITLE_MAX:
        raise FeedbackValidationError(f"反馈标题不能超过 {FEEDBACK_TITLE_MAX} 字")
    if len(description) > FEEDBACK_DESCRIPTION_MAX:
        raise FeedbackValidationError(f"反馈描述不能超过 {FEEDBACK_DESCRIPTION_MAX} 字")


async def create_feedback(
    db: AsyncSession,
    *,
    submitter_id: int,
    submitter_name: str,
    title: str,
    description: str,
    subtype: Optional[str] = None,
    severity: Optional[str] = None,
    page_path: Optional[str] = None,
    attachments=None,
) -> Tuple[Feedback, List[int]]:
    """创建反馈（flush，不 commit）；返回 (反馈行, 被通知的处理人 id 列表)。

    非法类型/严重程度/超长内容一律抛 FeedbackValidationError，不静默降级或截断。
    """
    _validate_content(title, description)
    if subtype is not None and subtype not in FEEDBACK_TYPES:
        raise FeedbackValidationError(f"反馈类型非法：{subtype}")
    if severity is not None and severity not in FEEDBACK_SEVERITIES:
        raise FeedbackValidationError(f"严重程度非法：{severity}")

    attachment_dicts = to_dicts(attachments)
    fb = Feedback(
        type=subtype if subtype in FEEDBACK_TYPES else "issue",
        severity=severity if severity in FEEDBACK_SEVERITIES else "low",
        page_path=page_path,
        title=title,
        description=description,
        attachments=attachment_dicts or None,
        status="pending",
        submitter_id=int(submitter_id),
        submitter_name=submitter_name or "",
    )
    db.add(fb)
    await db.flush()

    if attachment_dicts:
        svc = FileService(db)
        await svc.attach([a.get("key") for a in attachment_dicts], "feedback", str(fb.id))

    handler_ids: List[int] = []
    try:
        handler_ids = await insert_handler_notifications(db, fb)
    except Exception as e:
        logger.warning(f"[feedback] 插入处理人通知失败 feedback_id={fb.id}: {e}")
    return fb, handler_ids


async def delete_feedback_notifications(db: AsyncSession, feedback_id: int) -> None:
    """删除指向该反馈的未读处理人通知（撤销/删除反馈后避免悬空深链）。"""
    await db.execute(
        delete(Notification).where(
            Notification.ref_type == "feedback",
            Notification.ref_id == int(feedback_id),
            Notification.is_read.is_(False),
        )
    )


async def revoke_feedback(db: AsyncSession, *, feedback_id: int, user_id: int) -> dict:
    """撤销本人待处理的反馈（解绑附件后删除）。仅 status=pending 且提交人本人可撤销。"""
    fb = (await db.execute(
        select(Feedback).where(Feedback.id == int(feedback_id))
    )).scalar_one_or_none()
    if not fb:
        raise FeedbackRevokeError(f"反馈 #{feedback_id} 不存在")
    if int(fb.submitter_id) != int(user_id):
        raise FeedbackRevokeError("只能撤销自己提交的反馈")
    if fb.status != "pending":
        raise FeedbackRevokeError("该反馈已被处理，无法撤销；如需关闭请联系管理员")

    keys = [a.get("key") for a in (fb.attachments or []) if isinstance(a, dict) and a.get("key")]
    if keys:
        svc = FileService(db)
        await svc.detach(keys)

    await delete_feedback_notifications(db, fb.id)
    await db.delete(fb)
    await db.flush()
    return {"deleted": int(feedback_id)}
