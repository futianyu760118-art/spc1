"""定时备份调度器：每分钟检查配置，错过窗口自动补触发一次"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.basicdata.announcement import Notification
from app.models.basicdata.backup import BackupConfig
from app.models.basicdata.user import SysRole, SysUser
from app.services.backup.backup_service import backup_service
from app.services.backup.plan import last_due_time
from app.services.notification.notification_broker import publish_unread_update

logger = logging.getLogger(__name__)


class BackupScheduler:
    def __init__(self, interval_seconds: int = 60):
        self.running = False
        self.task = None
        self.interval_seconds = interval_seconds

    async def _run_check(self):
        try:
            async with AsyncSessionLocal() as db:
                config = await db.get(BackupConfig, 1)
                if not config or not config.enabled:
                    return
                now = datetime.now()
                due = last_due_time(frequency=config.frequency, schedule_time=config.schedule_time,
                                    weekday=config.weekday, now=now)
                if config.last_triggered_at and config.last_triggered_at >= due:
                    return
                # 互斥冲突则本轮跳过且不落 last_triggered_at，下一轮（60s 后）自动重试，避免误告警
                if backup_service.is_busy():
                    return
                config.last_triggered_at = now
                await db.commit()

            job_id = backup_service.run_backup(source="scheduled")
            job = backup_service.get_job(job_id)
            while job and job.status == "running":
                await asyncio.sleep(5)
                job = backup_service.get_job(job_id)
            if job and job.status != "ok":
                await self._notify_admins()
        except Exception as e:
            logger.error(f"[定时备份] 执行失败: {e}")

    async def _notify_admins(self):
        async with AsyncSessionLocal() as db:
            admin_ids = (await db.execute(
                select(SysUser.id).join(SysRole, SysUser.role_id == SysRole.id)
                .where(SysRole.role_code == "admin", SysUser.is_active.is_(True))
            )).scalars().all()
            for uid in admin_ids:
                db.add(Notification(
                    user_id=uid, type="backup_alert", title="定时备份失败",
                    content="定时备份任务失败，请到「基础数据与集成中心 → 备份管理」查看日志并处理。",
                    ref_type="backup", sender_name="系统", priority="important", is_read=False,
                ))
            await db.commit()
            for uid in admin_ids:
                await publish_unread_update(db, uid)

    async def _loop(self):
        while self.running:
            await self._run_check()
            await asyncio.sleep(self.interval_seconds)

    def start(self):
        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info("[定时备份] 调度器已启动")

    def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("[定时备份] 调度器已停止")


backup_scheduler = BackupScheduler(interval_seconds=60)
