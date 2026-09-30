"""通知 SSE 实时推送 — Redis pub/sub → SSE 桥接。

publish_unread_update: 供 API/service 层在通知变更后调用，推未读计数到 Redis。
subscribe_stream: 供 SSE 端点使用，长连接订阅 notif:{user_id} 并 yield SSE 帧。

事件约定（前端 MainLayout / 通知中心监听）：
- unread：未读计数帧（total/by_type），首帧快照、实时推送、重连补偿快照都用它；
- degraded：订阅断开进入退避重连，前端据此启动降级轮询；
- recovered：订阅恢复（此前发过 degraded 才发），前端据此停止轮询。

Redis 不可用/订阅中断时绝不结束流（流一结束浏览器 EventSource 会每 3s 重连形成风暴），
而是指数退避自动重订阅，期间只发心跳与 degraded，恢复后补一帧最新快照再发 recovered。
结构源自 app/services/material/stock_check_broker.py，重连与降级通知为通知域增强。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import (
    get_command_client,
    make_pubsub_client,
    note_failure,
    note_success,
)

from app.models.basicdata.announcement import Notification

logger = logging.getLogger(__name__)

CHANNEL_FMT = "notif:{user_id}"
HEARTBEAT_SEC = 15
# 首次失败立即重试(0)，此后指数退避封顶 60s：连接抖动时不打重连风暴
RECONNECT_BACKOFF_SEC = (0, 5, 10, 20, 30, 60)


async def compute_unread_counts(db: AsyncSession, user_id: int) -> dict:
    """计算某用户的未读计数 {total, by_type}。供 /unread-count 端点与 broker 复用。"""
    q = (
        select(Notification.type, func.count(Notification.id))
        .where(and_(Notification.user_id == user_id, Notification.is_read == False))  # noqa: E712
        .group_by(Notification.type)
    )
    rows = (await db.execute(q)).all()
    counts = {r[0]: r[1] for r in rows}
    total = sum(counts.values())
    return {"total": total, "by_type": counts}


async def publish_unread_update(db: AsyncSession, user_id: int) -> None:
    """通知变更后调用：计算该用户未读计数并 PUBLISH 到 notif:{user_id}。Redis 不可用则静默丢弃。"""
    client = get_command_client()
    if client is None:
        logger.warning("notification_broker.publish: redis unavailable, user_id=%s dropped", user_id)
        return
    try:
        payload = await compute_unread_counts(db, user_id)
        envelope = {
            "total": payload["total"],
            "by_type": payload["by_type"],
            "ts": datetime.utcnow().isoformat(),
        }
        await client.publish(
            CHANNEL_FMT.format(user_id=user_id),
            json.dumps(envelope, ensure_ascii=False),
        )
        note_success()
    except Exception as e:
        note_failure()
        logger.warning("notification_broker.publish failed user_id=%s: %s", user_id, e)


def _unread_chunk(payload: dict) -> str:
    return (
        "event: unread\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


def _control_chunk(event: str) -> str:
    return f"event: {event}\ndata: {{}}\n\n"


async def _snapshot(user_id: int) -> dict:
    """短命会话算未读计数，用完立刻归还连接池（SSE 流可能活几小时）。"""
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            return await compute_unread_counts(db, user_id)
    except Exception as e:
        logger.warning("notification_broker.subscribe snapshot failed: %s", e)
        return {"total": 0, "by_type": {}}


async def _open_pubsub(channel: str):
    """新建独立订阅连接；失败时释放半开资源并把异常抛给调用方。"""
    client = make_pubsub_client()
    pubsub = None
    try:
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub, client
    except BaseException:
        await _close_pubsub(pubsub, client)
        raise


async def _close_pubsub(pubsub, client) -> None:
    """释放订阅连接与专属客户端。"""
    if pubsub is not None:
        try:
            await pubsub.aclose()
        except Exception:
            pass
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            pass


async def subscribe_stream(
    user_id: int,
) -> AsyncGenerator[str, None]:
    """SSE 端点生成器。首帧 snapshot(当前未读计数)，后续 unread 事件 + 15s 心跳。

    订阅失败/中断不结束流，改为指数退避自动重订阅；期间发 degraded 让前端轮询兜底，
    恢复后补一帧最新快照(覆盖订阅空窗期)再发 recovered。快照用短命会话算完立刻归还,
    订阅循环只走 Redis:流可活几小时,持有调用方 db 会话会占住连接池的一条连接。
    """
    yield _unread_chunk(await _snapshot(user_id))

    channel = CHANNEL_FMT.format(user_id=user_id)
    pubsub = None
    client = None
    degraded = False
    retry_idx = 0

    async def _backoff_frames() -> AsyncGenerator[str, None]:
        """统一失败出口：首发 degraded 让前端轮询兜底，再退避等待（分片心跳保活）。"""
        nonlocal degraded, retry_idx
        if not degraded:
            degraded = True
            yield _control_chunk("degraded")
        delay = RECONNECT_BACKOFF_SEC[min(retry_idx, len(RECONNECT_BACKOFF_SEC) - 1)]
        retry_idx += 1
        while delay > 0:
            step = min(delay, HEARTBEAT_SEC)
            await asyncio.sleep(step)
            delay -= step
            yield ": keep-alive\n\n"

    try:
        while True:
            if pubsub is None:
                try:
                    pubsub, client = await _open_pubsub(channel)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("notification_broker.subscribe failed (%s)，退避重连", e)
                    async for chunk in _backoff_frames():
                        yield chunk
                    continue
                # 订阅成功：补一帧最新快照(覆盖订阅空窗期)，此前降级过再解除
                yield _unread_chunk(await _snapshot(user_id))
                if degraded:
                    degraded = False
                    yield _control_chunk("recovered")
                continue

            try:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=HEARTBEAT_SEC
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("notification_broker.subscribe loop error (%s)，退避重连", e)
                await _close_pubsub(pubsub, client)
                pubsub = None
                client = None
                async for chunk in _backoff_frames():
                    yield chunk
                continue
            retry_idx = 0
            if msg is None:
                yield ": keep-alive\n\n"
                continue
            data = msg.get("data") if isinstance(msg, dict) else None
            if not data or not isinstance(data, str):
                continue
            try:
                envelope = json.loads(data)
            except Exception:
                continue
            yield _unread_chunk({
                "total": envelope.get("total", 0),
                "by_type": envelope.get("by_type", {}),
            })
    except asyncio.CancelledError:
        pass
    finally:
        await _close_pubsub(pubsub, client)
