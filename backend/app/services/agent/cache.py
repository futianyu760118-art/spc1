"""智能体能力读路径缓存（进程内 TTL）。

权限配置写入后调用 invalidate_agent 失效本实例；多实例下其它实例最多在
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


def invalidate_agent(agent_id: int) -> None:
    prefix = f"agent:{int(agent_id)}:"
    for key in [k for k in _store if k.startswith(prefix)]:
        _store.pop(key, None)


def clear() -> None:
    _store.clear()
