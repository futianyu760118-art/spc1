"""待排快照定时刷新调度器。

待排工作台/排产台账读的是「订单排产快照表」, 而快照不会在查询时自动生成。
若不定期刷新, 新进入月份的订单不会出现在排产池里(台账条数偏少)。

本调度器每天固定时间(默认 03:30)刷新「当前月 + 未来 N 个月」的待排快照,
复用排产模块的源订单查询与快照生成逻辑, 保证数据一致。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_MAX_SLEEP_SECONDS = 1800


def _month_range(months_ahead: int) -> list[tuple[int, int]]:
    today = date.today()
    year, month = today.year, today.month
    result: list[tuple[int, int]] = []
    for _ in range(months_ahead + 1):
        result.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return result


class SnapshotRefreshScheduler:
    """待排快照每日定时刷新调度器。"""

    def __init__(self):
        self.running = False
        self.task: asyncio.Task | None = None
        self.last_run_at: datetime | None = None

    def _next_run_at(self, now: datetime | None = None) -> datetime:
        settings = get_settings()
        now = now or datetime.now()
        target = now.replace(
            hour=settings.snapshot_refresh_hour,
            minute=settings.snapshot_refresh_minute,
            second=0, microsecond=0,
        )
        if target <= now:
            target += timedelta(days=1)
        return target

    async def _run_once(self) -> None:
        settings = get_settings()
        months = _month_range(settings.snapshot_refresh_months_ahead)
        logger.info(f"[待排快照刷新] 开始 - {datetime.now():%Y-%m-%d %H:%M:%S} 月份={months}")
        # 延迟导入, 避免与 api 模块产生导入环
        from app.api.v1.production.schedule_plans import (
            _ensure_order_snapshot_table,
            _query_todo_snapshot_source_rows,
            _refresh_order_schedule_snapshots,
        )

        total = 0
        try:
            async with AsyncSessionLocal() as db:
                await _ensure_order_snapshot_table(db)
                for (year, month) in months:
                    try:
                        rows = await _query_todo_snapshot_source_rows(
                            db, year=year, month=month, keyword=None, risk_level=None,
                            limit=settings.snapshot_refresh_limit,
                        )
                        await _refresh_order_schedule_snapshots(db, rows, force_refresh=True)
                        total += len(rows)
                        logger.info(f"[待排快照刷新] {year}-{month:02d} 刷新 {len(rows)} 条")
                    except Exception as e:
                        await db.rollback()
                        logger.error(f"[待排快照刷新] {year}-{month:02d} 失败: {e}", exc_info=True)
                await db.commit()
            self.last_run_at = datetime.now()
            logger.info(f"[待排快照刷新] 完成, 共刷新 {total} 条")
        except Exception as e:
            logger.error(f"[待排快照刷新] 执行失败: {e}", exc_info=True)

    async def _loop(self) -> None:
        if not get_settings().snapshot_refresh_enabled:
            logger.info("[待排快照刷新] 已禁用(snapshot_refresh_enabled=false), 不启动")
            return
        logger.info(
            "[待排快照刷新] 调度器启动 - 每天 %02d:%02d, 刷新当月+未来%d个月",
            get_settings().snapshot_refresh_hour,
            get_settings().snapshot_refresh_minute,
            get_settings().snapshot_refresh_months_ahead,
        )
        while self.running:
            try:
                target = self._next_run_at()
                wait = max((target - datetime.now()).total_seconds(), 1)
                while self.running and wait > 0:
                    chunk = min(wait, _MAX_SLEEP_SECONDS)
                    await asyncio.sleep(chunk)
                    wait -= chunk
                if not self.running:
                    break
                await self._run_once()
            except asyncio.CancelledError:
                logger.info("[待排快照刷新] 收到取消信号, 退出")
                break
            except Exception as e:
                logger.error(f"[待排快照刷新] 循环异常, 继续运行: {e}", exc_info=True)
                await asyncio.sleep(60)

    def start(self) -> None:
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._loop())
            logger.info("[待排快照刷新] 已启动")

    def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("[待排快照刷新] 已停止")


snapshot_refresh_scheduler = SnapshotRefreshScheduler()
