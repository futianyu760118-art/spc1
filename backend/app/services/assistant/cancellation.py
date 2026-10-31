"""取消事件管理 — 客户端断连 / 超时触发"""

import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CancellationRegistry:
    _events: Dict[str, asyncio.Event] = {}
    _reasons: Dict[str, str] = {}
    _lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get_or_create(cls, session_id: str) -> asyncio.Event:
        async with cls._get_lock():
            ev = cls._events.get(session_id)
            if ev is None:
                ev = asyncio.Event()
                cls._events[session_id] = ev
            return ev

    @classmethod
    def get_sync(cls, session_id: str) -> Optional[asyncio.Event]:
        return cls._events.get(session_id)

    @classmethod
    def is_cancelled(cls, session_id: str) -> bool:
        ev = cls._events.get(session_id)
        return ev is not None and ev.is_set()

    @classmethod
    def trigger(cls, session_id: str, reason: str = "external") -> None:
        ev = cls._events.get(session_id)
        if ev is not None and not ev.is_set():
            ev.set()
            cls._reasons[session_id] = reason
            logger.info(f"[cancel] session={session_id} reason={reason}")

    @classmethod
    def reason(cls, session_id: str) -> str:
        return cls._reasons.get(session_id, "")

    @classmethod
    def cleanup(cls, session_id: str) -> None:
        cls._events.pop(session_id, None)
        cls._reasons.pop(session_id, None)

    @classmethod
    def clear_all(cls) -> None:
        cls._events.clear()
        cls._reasons.clear()
