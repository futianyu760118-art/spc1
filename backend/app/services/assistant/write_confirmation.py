"""写操作确认单 — Redis 待确认记录（10 分钟过期，原子消费，多实例安全）。

- create：写入「旧值 → 新值」差异与续跑上下文，返回 confirmation_id；
- consume：Lua 原子 GET+DEL，同一确认单只允许执行一次（多实例下唯一执行点）；
- cancel：消费并标记取消，不产生任何写入。

Redis 不可用时降级为进程内存（与 session_store 同策略，仅本实例有效）。
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from app.core.redis_client import get_command_client, note_failure, note_success

logger = logging.getLogger(__name__)

CONFIRMATION_TTL_S = 600  # 10 分钟过期
KEY_PREFIX = "assistant:write_confirmation:"

# 原子消费：GET 后立刻 DEL，并发 / 多实例下只有一个调用方能拿到值
_CONSUME_SCRIPT = """
local v = redis.call('GET', KEYS[1])
if v then redis.call('DEL', KEYS[1]) end
return v
"""

_memory_store: Dict[str, str] = {}


def _key(confirmation_id: str) -> str:
    return f"{KEY_PREFIX}{confirmation_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_confirmation(record: Dict[str, Any]) -> Dict[str, Any]:
    """写入待确认记录；自动生成 id / created_at / expires_at。返回完整记录（含 id）。"""
    confirmation_id = f"wc-{uuid4().hex[:16]}"
    created_at = _now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=CONFIRMATION_TTL_S)).isoformat()
    full = {
        **record,
        "confirmation_id": confirmation_id,
        "created_at": created_at,
        "expires_at": expires_at,
        "ttl_s": CONFIRMATION_TTL_S,
    }
    key = _key(confirmation_id)
    payload = json.dumps(full, ensure_ascii=False, default=str)
    client = get_command_client()
    if client is None:
        _memory_store[key] = payload
        return full
    try:
        await client.setex(key, CONFIRMATION_TTL_S, payload)
        note_success()
    except Exception as e:
        note_failure()
        logger.error(f"写入写操作确认单失败（降级内存）: {e}")
        _memory_store[key] = payload
    return full


async def get_confirmation(confirmation_id: str) -> Optional[Dict[str, Any]]:
    """读取确认单（不消费），供校验 / 展示。"""
    if not confirmation_id:
        return None
    key = _key(confirmation_id)
    client = get_command_client()
    raw: Optional[str] = None
    if client is None:
        raw = _memory_store.get(key)
    else:
        try:
            raw = await client.get(key)
            note_success()
        except Exception as e:
            note_failure()
            logger.error(f"读取写操作确认单失败: {e}")
            raw = _memory_store.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        logger.error(f"解析写操作确认单失败: {e}")
        return None


async def consume_confirmation(confirmation_id: str) -> Optional[Dict[str, Any]]:
    """原子消费确认单：返回记录并删除；已被消费 / 已过期返回 None。"""
    if not confirmation_id:
        return None
    key = _key(confirmation_id)
    client = get_command_client()
    raw: Optional[str] = None
    if client is None:
        raw = _memory_store.pop(key, None)
    else:
        try:
            raw = await client.eval(_CONSUME_SCRIPT, 1, key)
            note_success()
        except Exception as e:
            note_failure()
            logger.error(f"消费写操作确认单失败（降级内存）: {e}")
            raw = _memory_store.pop(key, None)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        logger.error(f"解析写操作确认单失败: {e}")
        return None
