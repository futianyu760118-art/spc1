"""智能体上下文读路径缓存（进程内 TTL）。

缓存键含成员 config_version（userctx:{user_id}:{version_key}），勾选变更
与成员编辑 bump config_version 后旧键自然失效；多实例下其它实例最多在
AGENT_SCOPE_CACHE_TTL_SECONDS 后自然过期，符合设计「读路径 5 分钟 TTL」。
"""

import time
from typing import Any, Dict, Optional

from app.core.config import get_settings

_store: Dict[str, tuple[float, Any]] = {}


def _ttl() -> float:
    return max(int(get_settings().AGENT_SCOPE_CACHE_TTL_SECONDS), 1)


def get(key: str) -> Optional[Any]:
    item = _store.get(key)
    if not item:
        return None
    expires_at, value = item
    if expires_at <= time.time():
        _store.pop(key, None)
        return None
    return value


def set(key: str, value: Any) -> None:
    _store[key] = (time.time() + _ttl(), value)


def clear() -> None:
    _store.clear()
