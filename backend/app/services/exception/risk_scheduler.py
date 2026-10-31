"""风险评估定时调度器 — 每小时自动执行风险评估"""

import asyncio
import logging
from datetime import datetime

from app.core.database import AsyncSessionLocal
from app.services.exception.risk_engine import RiskEngine

logger = logging.getLogger(__name__)


class RiskAssessmentScheduler:
    """风险评估定时调度器"""

    def __init__(self, interval_hours: int = 1):
        self.running = False
        self.task = None
        self.interval_hours = interval_hours

    async def _run_assessment(self):
        """执行一次风险评估"""
        logger.info(f"[风险评估调度] 开始执行 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            async with AsyncSessionLocal() as db:
                engine = RiskEngine(db)
                result = await engine.assess_all_orders(operator="scheduler")
                await db.commit()
                logger.info(
                    f"[风险评估调度] 完成: 评估{result['assessed']}个订单, "
                    f"红{result['red_count']}/黄{result['yellow_count']}/绿{result['green_count']}"
                )
        except Exception as e:
            logger.error(f"[风险评估调度] 执行失败: {e}")

    async def _loop(self):
        """调度循环：每 interval_hours 小时执行一次"""
        while self.running:
            await self._run_assessment()
            await asyncio.sleep(self.interval_hours * 3600)

    def start(self):
        """启动调度器"""
        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info(f"[风险评估调度] 已启动，每{self.interval_hours}小时执行一次")

    def stop(self):
        """停止调度器"""
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("[风险评估调度] 已停止")


# 全局调度器实例
risk_scheduler = RiskAssessmentScheduler(interval_hours=1)
