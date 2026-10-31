"""排产计划变更检测调度器。

已排产订单的「出货计划/数量/UPPH」发生变更时, 需把对应排产计划标记为「待重排」,
否则不会出现在待重排列表里。检测逻辑见 ProductionChangeService。

本调度器每隔固定时间(默认 1 小时)自动跑一次变更检测, 随应用启停。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class ProductionChangeScheduler:
    """排产计划变更检测调度器。"""

    def __init__(self):
        self.running = False
        self.task: asyncio.Task | None = None
        self.last_run_at: datetime | None = None

    async def _run_once(self) -> None:
        from app.services.production.production_change_service import ProductionChangeService

        try:
            async with AsyncSessionLocal() as db:
                logs = await ProductionChangeService(db).detect_and_log_sale_order_line_changes()
            self.last_run_at = datetime.now()
            if logs:
                logger.info(f"[变更检测] 检测到 {len(logs)} 条订单行变更并标记待重排")
        except Exception as e:
            logger.error(f"[变更检测] 执行失败: {e}", exc_info=True)

    async def _loop(self) -> None:
        settings = get_settings()
        if not settings.change_detect_enabled:
            logger.info("[变更检测] 已禁用(change_detect_enabled=false), 不启动")
            return
        interval = max(int(settings.change_detect_interval_hours or 1), 1) * 3600
        logger.info("[变更检测] 调度器启动 - 每 %d 小时执行一次", interval // 3600)
        # 启动后稍等片刻(避开启动高峰)再跑首次
        await asyncio.sleep(60)
        while self.running:
            try:
                await self._run_once()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[变更检测] 收到取消信号, 退出")
                break
            except Exception as e:
                logger.error(f"[变更检测] 循环异常, 继续运行: {e}", exc_info=True)
                await asyncio.sleep(60)

    def start(self) -> None:
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._loop())
            logger.info("[变更检测] 已启动")

    def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("[变更检测] 已停止")


production_change_scheduler = ProductionChangeScheduler()
