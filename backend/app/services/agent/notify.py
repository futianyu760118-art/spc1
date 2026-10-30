"""智能体中心通知：站内信 + 企微 textcard + SSE 未读计数。"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.announcement import Notification
from app.services.notification.notification_broker import publish_unread_update

logger = logging.getLogger(__name__)

MAX_TITLE = 256
MAX_CONTENT = 512


def _clip(value: Optional[str], limit: int) -> str:
    text = str(value or "")
    return text[:limit]


async def notify_user(
    db: AsyncSession,
    *,
    user_id: int,
    title: str,
    content: str = "",
    notif_type: str = "agent_task",
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
    ref_no: Optional[str] = None,
    priority: str = "normal",
    sender_id: Optional[int] = None,
    sender_name: Optional[str] = None,
    wecom_path: Optional[str] = None,
    wecom: bool = False,
) -> None:
    """写站内信并推送未读数；企微失败只记日志，不影响主流程。"""
    notification = Notification(
        user_id=int(user_id),
        type=notif_type,
        title=_clip(title, MAX_TITLE),
        content=_clip(content, MAX_CONTENT),
        ref_type=ref_type,
        ref_id=ref_id,
        ref_no=ref_no,
        sender_id=sender_id,
        sender_name=sender_name,
        priority=priority,
        is_read=False,
    )
    db.add(notification)
    await db.flush()
    try:
        await publish_unread_update(db, int(user_id))
    except Exception as exc:
        logger.warning("[agent-notify] SSE 未读推送失败 user=%s: %s", user_id, exc)
    if wecom and wecom_path:
        try:
            from app.services.common.approval_notify import send_approval_wecom_textcard
            await send_approval_wecom_textcard(
                db,
                user_ids=[int(user_id)],
                title=title,
                description=content or title,
                path=wecom_path,
                btn_text="查看任务",
            )
        except Exception as exc:
            logger.warning("[agent-notify] 企微推送失败 user=%s: %s", user_id, exc)
