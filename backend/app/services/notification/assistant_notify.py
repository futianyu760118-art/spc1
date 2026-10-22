"""AI 助手数据变更通知：注册表、受管后台任务、站内信落库与未读推送。"""

import asyncio
import hashlib
import logging
from typing import Dict, List, Optional, Set
from uuid import uuid4

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_command_client, note_failure, note_success
from app.models.basicdata.announcement import Notification
from app.models.basicdata.user import SysUser
from app.services.common.permission_users import user_ids_with_permission
from app.services.notification.notification_broker import publish_unread_updates
from app.services.notification.text_utils import (
    NOTIFICATION_CONTENT_MAX,
    NOTIFICATION_REF_NO_MAX,
    NOTIFICATION_TITLE_MAX,
    clip_text,
)

logger = logging.getLogger(__name__)

BIZ_NOTIFY_CONFIG: Dict[str, dict] = {
    "order": {
        "permission": "orders.list",
        "permission_action": "read",
        "frontend_path": "/orders/{no}",
        "label": "订单",
        "query_paths": ["/external/orders/list"],
        "available_fields": [
            "order_no", "line_no", "customer", "customer_code", "product_code", "product_name",
            "order_qty", "completed_qty", "order_amount", "status", "erp_status",
            "delivery_completed_date", "risk_level", "risk_probability", "promised_date",
            "planned_start_date", "shipping_plan", "customer_inspection_date", "owner", "updated_at",
        ],
    },
}

ACTION_CONFIG: Dict[str, dict] = {
    "update": {"type": "assistant_update", "label": "更新", "deep_link": True},
    "create": {"type": "assistant_create", "label": "新增", "deep_link": True},
    "delete": {"type": "assistant_delete", "label": "删除", "deep_link": False},
}

GAP_RATE_LIMIT_PER_HOUR = 20
GAP_DEDUP_TTL_S = 24 * 3600

_GAP_RATE_LUA = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then redis.call('EXPIRE', KEYS[1], 3600) end
return c
"""

_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

_tasks: Set[asyncio.Task] = set()
_redis_degraded_logged = False


def _mark_redis_degraded(detail: str) -> None:
    global _redis_degraded_logged
    if not _redis_degraded_logged:
        _redis_degraded_logged = True
        logger.warning("notify_degraded reason=redis_unavailable detail=%s", detail)


def _mark_redis_ok() -> None:
    global _redis_degraded_logged
    if _redis_degraded_logged:
        _redis_degraded_logged = False
        logger.info("notify_recovered reason=redis_available")


def _schedule(coro) -> None:
    try:
        task = asyncio.create_task(coro)
    except Exception as e:
        coro.close()
        logger.error("notification schedule failed: %s", e)
        return
    _tasks.add(task)

    def _on_done(done: asyncio.Task) -> None:
        _tasks.discard(done)
        try:
            error = done.exception()
        except asyncio.CancelledError:
            return
        if error:
            logger.error("notification task failed: %s", error)

    task.add_done_callback(_on_done)


async def flush_notifications() -> None:
    pending = list(_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def notify_agent_change(*, biz_type: str, biz_no: str, action: str,
                        operator_user_id: str) -> None:
    cfg = BIZ_NOTIFY_CONFIG.get(biz_type)
    if cfg is None:
        logger.warning("notify_skip reason=unknown_biz biz_type=%s action=%s", biz_type, action)
        return
    if action not in ACTION_CONFIG:
        logger.warning("notify_skip reason=unknown_action biz_type=%s action=%s", biz_type, action)
        return
    if not str(biz_no or "").strip():
        logger.warning("notify_skip reason=no_biz_no biz_type=%s action=%s", biz_type, action)
        return
    _schedule(_send_change(biz_type, str(biz_no), action, str(operator_user_id or "")))


def notify_agent_gap(*, biz_type: str, biz_no: str, missing_keys: List[str],
                     missing_labels: List[str], initiator_user_id: str) -> None:
    if biz_type not in BIZ_NOTIFY_CONFIG:
        logger.warning("notify_skip reason=unknown_biz biz_type=%s", biz_type)
        return
    if not str(biz_no or "").strip():
        logger.warning("notify_skip reason=no_biz_no biz_type=%s", biz_type)
        return
    if not missing_keys:
        logger.warning("notify_skip reason=no_missing_keys biz_type=%s biz_no=%s",
                       biz_type, biz_no)
        return
    _schedule(_send_gap(
        biz_type, str(biz_no), list(missing_keys), list(missing_labels),
        str(initiator_user_id or ""),
    ))


async def _operator_identity(db, user_id: str):
    if not str(user_id or "").isdigit():
        return None, None
    row = (
        await db.execute(
            select(SysUser.id, SysUser.display_name).where(SysUser.id == int(user_id))
        )
    ).one_or_none()
    if row is None:
        return None, None
    return int(row[0]), row[1]


async def _recipients(db, cfg: dict) -> List[int]:
    return await user_ids_with_permission(
        db, cfg["permission"], cfg.get("permission_action", "read")
    )


async def _send_change(biz_type: str, biz_no: str, action: str, operator_user_id: str) -> None:
    cfg = BIZ_NOTIFY_CONFIG[biz_type]
    act = ACTION_CONFIG[action]
    try:
        async with AsyncSessionLocal() as db:
            recipients = await _recipients(db, cfg)
            if not recipients:
                logger.info("notify_sent biz_type=%s biz_no=%s action=%s recipients=0",
                            biz_type, biz_no, action)
                return
            operator_id, operator_name = await _operator_identity(db, operator_user_id)
            label = cfg["label"]
            title = clip_text(
                f"AI 助手{act['label']}{label} {biz_no}", NOTIFICATION_TITLE_MAX
            )
            content = clip_text(
                f"{operator_name or '用户'} 通过 AI 智能助手{act['label']}了该{label}",
                NOTIFICATION_CONTENT_MAX,
            )
            db.add_all([
                Notification(
                    user_id=uid,
                    type=act["type"],
                    title=title,
                    content=content,
                    ref_type=biz_type,
                    ref_no=clip_text(biz_no, NOTIFICATION_REF_NO_MAX),
                    sender_id=operator_id,
                    sender_name=clip_text(operator_name, 64) if operator_name else None,
                    priority="normal",
                    is_read=False,
                )
                for uid in recipients
            ])
            await db.commit()
            await publish_unread_updates(db, recipients)
        logger.info("notify_sent biz_type=%s biz_no=%s action=%s recipients=%s",
                    biz_type, biz_no, action, len(recipients))
    except Exception as e:
        logger.error("notify_failed biz_type=%s biz_no=%s action=%s error=%s",
                     biz_type, biz_no, action, e)


def _gap_key(biz_type: str, biz_no: str, missing_keys: List[str]) -> str:
    digest = hashlib.sha1("|".join(sorted(missing_keys)).encode("utf-8")).hexdigest()[:16]
    return f"assistant_gap:{biz_type}:{biz_no}:{digest}"


async def claim_slot(key: str, value: str) -> Optional[bool]:
    """True=claimed，False=已被占用，None=Redis 不可用（放行）。"""
    client = get_command_client()
    if client is None:
        _mark_redis_degraded("claim_slot")
        return None
    try:
        claimed = bool(await client.set(key, value, nx=True, ex=GAP_DEDUP_TTL_S))
        _mark_redis_ok()
        note_success()
        return claimed
    except Exception as e:
        note_failure()
        _mark_redis_degraded("claim_slot_error")
        logger.warning("claim_slot failed: %s", e)
        return None


async def release_slot(key: str, value: str) -> None:
    client = get_command_client()
    if client is None:
        return
    try:
        await client.eval(_RELEASE_LUA, 1, key, value)
        _mark_redis_ok()
        note_success()
    except Exception as e:
        note_failure()
        _mark_redis_degraded("release_slot_error")
        logger.warning("release_slot failed: %s", e)


async def _allow_gap_event(initiator_user_id: str) -> bool:
    if not initiator_user_id.isdigit():
        return True
    client = get_command_client()
    if client is None:
        _mark_redis_degraded("rate_limit")
        return True
    key = f"assistant_gap_user:{initiator_user_id}"
    try:
        count = int(await client.eval(_GAP_RATE_LUA, 1, key))
        _mark_redis_ok()
        note_success()
        return count <= GAP_RATE_LIMIT_PER_HOUR
    except Exception as e:
        note_failure()
        _mark_redis_degraded("rate_limit_error")
        logger.warning("gap rate limit failed: %s", e)
        return True


async def _send_gap(biz_type: str, biz_no: str, missing_keys: List[str],
                    missing_labels: List[str], initiator_user_id: str) -> None:
    cfg = BIZ_NOTIFY_CONFIG[biz_type]
    key = _gap_key(biz_type, biz_no, missing_keys)
    batch_id = uuid4().hex[:12]
    claimed: Optional[bool] = None
    committed = False
    recipients_snapshot: List[int] = []
    try:
        # 延迟导入：ai_config 存在既有包级循环导入，避免本模块被直接导入时触发
        from app.services.ai_config import ASSISTANT_SCOPE, get_scope_config

        enabled = True
        try:
            async with AsyncSessionLocal() as db:
                rt = await get_scope_config(db, ASSISTANT_SCOPE)
            enabled = bool(rt.get("gap_notify_enabled", True))
        except Exception as e:
            logger.warning("notify_degraded reason=config_read_failed error=%s", e)
        if not enabled:
            logger.info("notify_skip reason=disabled biz_type=%s biz_no=%s", biz_type, biz_no)
            return

        claimed = await claim_slot(key, batch_id)
        if claimed is False:
            logger.info("notify_dedup_hit biz_type=%s biz_no=%s", biz_type, biz_no)
            return
        if not await _allow_gap_event(initiator_user_id):
            if claimed:
                await release_slot(key, batch_id)
            logger.info("notify_rate_limited biz_type=%s biz_no=%s initiator=%s",
                        biz_type, biz_no, initiator_user_id)
            return

        async with AsyncSessionLocal() as db:
            recipients = await _recipients(db, cfg)
            recipients_snapshot = list(recipients)
            if not recipients:
                if claimed:
                    await release_slot(key, batch_id)
                logger.info("notify_sent biz_type=%s biz_no=%s action=gap recipients=0",
                            biz_type, biz_no)
                return
            labels = "、".join(missing_labels[:10])
            if len(missing_labels) > 10:
                labels += f" 等 {len(missing_labels)} 项"
            title = clip_text(f"{cfg['label']} {biz_no} 信息不完整", NOTIFICATION_TITLE_MAX)
            content = clip_text(f"缺少：{labels}", NOTIFICATION_CONTENT_MAX)
            db.add_all([
                Notification(
                    user_id=uid,
                    type="assistant_gap",
                    title=title,
                    content=content,
                    ref_type=biz_type,
                    ref_no=clip_text(biz_no, NOTIFICATION_REF_NO_MAX),
                    priority="normal",
                    is_read=False,
                )
                for uid in recipients
            ])
            await db.commit()
            committed = True
            await publish_unread_updates(db, recipients)
        logger.info("notify_sent biz_type=%s biz_no=%s action=gap recipients=%s batch=%s",
                    biz_type, biz_no, len(recipients), batch_id)
    except asyncio.CancelledError:
        if claimed and not committed:
            await release_slot(key, batch_id)
        raise
    except Exception as e:
        if committed:
            logger.error(
                "notify_publish_failed biz_type=%s biz_no=%s batch=%s recipients=%s missing=%s error=%s",
                biz_type, biz_no, batch_id, len(recipients_snapshot), missing_keys, e,
            )
        else:
            if claimed:
                await release_slot(key, batch_id)
            logger.error(
                "notify_failed_claimed biz_type=%s biz_no=%s batch=%s recipients=%s missing=%s error=%s",
                biz_type, biz_no, batch_id, len(recipients_snapshot), missing_keys, e,
            )
