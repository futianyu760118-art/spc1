"""MRP 定时调度器 — 每晚 02:00 全量运算（手写 asyncio 循环，非 APScheduler）。"""

import asyncio
import logging
from datetime import date, datetime

from app.services.mrp.engine import mrp_engine

logger = logging.getLogger(__name__)

SCHEDULE_HOUR = 2
TICK_SECONDS = 300


class MrpScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_date: date | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._last_run_date = None
        self._task = asyncio.create_task(self._loop())
        logger.info("[MRP调度] 已启动，每晚 %02d:00 全量运算", SCHEDULE_HOUR)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[MRP调度] 已停止")

    async def _loop(self) -> None:
        while self._running:
            try:
                now = datetime.now()
                if now.hour >= SCHEDULE_HOUR and self._last_run_date != now.date():
                    self._last_run_date = now.date()
                    try:
                        run = await mrp_engine.create_run_and_launch("scheduled", "system")
                        logger.info("[MRP调度] 已触发全量运算 run=%s", run.run_no)
                    except RuntimeError as exc:
                        logger.warning("[MRP调度] 跳过: %s", exc)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[MRP调度] 循环异常")
            await asyncio.sleep(TICK_SECONDS)


mrp_scheduler = MrpScheduler()
