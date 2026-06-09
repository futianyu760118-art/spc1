"""会话存储 — Redis 存储对话历史，支持服务端会话管理"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 会话配置
SESSION_TTL = 1800  # 30 分钟过期
MAX_HISTORY_LENGTH = 20  # 最多保留 20 条消息

_redis_client = None


def _get_redis():
    """懒加载 Redis 客户端"""
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            from app.core.config import get_settings
            settings = get_settings()
            _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            _redis_client.ping()
            logger.info("Session store: Redis 连接成功")
        except Exception as e:
            logger.warning(f"Session store: Redis 不可用 ({e})，使用内存存储")
            _redis_client = None
    return _redis_client


# 内存 fallback（Redis 不可用时）
_memory_store: Dict[str, str] = {}


def _session_key(session_id: str) -> str:
    return f"assistant:session:{session_id}"


async def get_history(session_id: str) -> List[Dict[str, Any]]:
    """获取会话历史"""
    if not session_id:
        return []

    try:
        r = _get_redis()
        if r:
            data = r.get(_session_key(session_id))
        else:
            data = _memory_store.get(_session_key(session_id))

        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"获取会话历史失败: {e}")

    return []


async def save_history(session_id: str, history: List[Dict[str, Any]]) -> None:
    """保存会话历史"""
    if not session_id:
        return

    # 限制历史长度
    if len(history) > MAX_HISTORY_LENGTH:
        history = history[-MAX_HISTORY_LENGTH:]

    try:
        data = json.dumps(history, ensure_ascii=False, default=str)
        r = _get_redis()
        if r:
            r.setex(_session_key(session_id), SESSION_TTL, data)
        else:
            _memory_store[_session_key(session_id)] = data
    except Exception as e:
        logger.error(f"保存会话历史失败: {e}")


async def append_messages(
    session_id: str,
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """追加消息到会话历史并返回完整历史"""
    history = await get_history(session_id)
    history.extend(messages)

    # 限制长度
    if len(history) > MAX_HISTORY_LENGTH:
        history = history[-MAX_HISTORY_LENGTH:]

    await save_history(session_id, history)
    return history


async def clear_session(session_id: str) -> None:
    """清除会话"""
    if not session_id:
        return
    try:
        r = _get_redis()
        if r:
            r.delete(_session_key(session_id))
        else:
            _memory_store.pop(_session_key(session_id), None)
    except Exception as e:
        logger.error(f"清除会话失败: {e}")
