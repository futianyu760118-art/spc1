"""订单工价缺口每日提醒调度器。

工作日(周一~周五) 固定时间(默认 08:30)检查工价缺口, 有缺口则通过企业微信
推送给配置的收件人(带免登分享链接)。周末跳过。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.services.production.order_wage_gap_service import send_daily_wage_reminder

logger = logging.getLogger(__name__)

# 距下次执行超过该秒数时, 分段睡眠以便能及时响应停止信号
_MAX_SLEEP_SECONDS = 1800


class WageReminderScheduler:
    """订单工价缺口每日提醒调度器。"""

    def __init__(self):
        self.running = False
        self.task: asyncio.Task | None = None
        self.last_run_at: datetime | None = None

    def _next_run_at(self, now: datetime | None = None) -> datetime:
        settings = get_settings()
        now = now or datetime.now()
        target = now.replace(
            hour=settings.wage_reminder_hour,
            minute=settings.wage_reminder_minute,
            second=0,
            microsecond=0,
        )
        if target <= now:
            target += timedelta(days=1)
        # 跳过周六(5)/周日(6)
        while target.weekday() >= 5:
            target += timedelta(days=1)
        return target

    async def _run_once(self) -> None:
        settings = get_settings()
        usernames = [n.strip() for n in (settings.wage_reminder_usernames or "").split(",") if n.strip()]
        logger.info(f"[工价提醒] 开始执行 - {datetime.now():%Y-%m-%d %H:%M:%S} 收件人={usernames}")
        try:
            async with AsyncSessionLocal() as db:
                result = await send_daily_wage_reminder(db, usernames)
                await db.commit()
            self.last_run_at = datetime.now()
            logger.info(f"[工价提醒] 执行完成: {result}")
        except Exception as e:
            logger.error(f"[工价提醒] 执行失败: {e}", exc_info=True)

    async def _loop(self) -> None:
        if not get_settings().wage_reminder_enabled:
            logger.info("[工价提醒] 已禁用(wage_reminder_enabled=false), 调度器不启动")
            return
        logger.info(
            "[工价提醒] 调度器启动 - 工作日 %02d:%02d 推送",
            get_settings().wage_reminder_hour,
            get_settings().wage_reminder_minute,
        )
        while self.running:
            try:
                target = self._next_run_at()
                wait = max((target - datetime.now()).total_seconds(), 1)
                logger.info("[工价提醒] 下次执行时间: %s (%.1f 分钟后)", target, wait / 60)
                while self.running and wait > 0:
                    chunk = min(wait, _MAX_SLEEP_SECONDS)
                    await asyncio.sleep(chunk)
                    wait -= chunk
                if not self.running:
                    break
                await self._run_once()
            except asyncio.CancelledError:
                logger.info("[工价提醒] 收到取消信号, 退出")
                break
            except Exception as e:
                logger.error(f"[工价提醒] 循环异常, 继续运行: {e}", exc_info=True)
                await asyncio.sleep(60)

    def start(self) -> None:
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._loop())
            logger.info("[工价提醒] 已启动")

    def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("[工价提醒] 已停止")


wage_reminder_scheduler = WageReminderScheduler()
