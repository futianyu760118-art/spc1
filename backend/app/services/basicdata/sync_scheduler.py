"""
ERP 定时同步调度器
支持配置化的同步策略（间隔、策略、时间窗口、优先级）
"""

import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timedelta, time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.config import get_settings
from app.services.basicdata.erp_sync_service import ERPSyncService
from app.models.basicdata.sync_sql_config import SyncSqlConfig
from app.models.basicdata.sync_log import SyncLog

logger = logging.getLogger(__name__)
settings = get_settings()


class SyncScheduler:
    """配置化定时同步调度器"""

    def __init__(self):
        self.running = False
        self.task = None
        self.sync_method_map = {
            "orders": "sync_orders",
            "order_details": "sync_order_details",
            "materials": "sync_materials",
            "purchase_orders": "sync_purchase_orders",
            "customers": "sync_customers",
            "suppliers": "sync_suppliers",
            "materials_masterdata": "sync_materials_masterdata",
            "skus": "sync_skus",
            "products": "sync_products",
            "boms": "sync_boms",
            "bom_details": "sync_bom_details",
            "warehouses": "sync_warehouses",
            "locations": "sync_locations",
            "processes": "sync_processes",
            "organizations": "sync_organizations",
            "positions": "sync_positions",
            "employees": "sync_employees",
            "purchase_invoices": "sync_purchase_invoices",
            "payment_applies": "sync_payment_applies",
            "quality_issues": "sync_quality_issues",
            "mrp_plan_orders": "sync_mrp_plan_orders",
            "production_task_orders": "sync_production_task_orders",
            "inventory": "sync_inventory",
            "subcontract_orders": "sync_subcontract_orders",
            "subcontract_order_details": "sync_subcontract_order_details",
        }

    async def _load_sync_configs(self, db: AsyncSession) -> list[SyncSqlConfig]:
        """从数据库加载所有启用的同步配置，按优先级排序"""
        result = await db.execute(
            select(SyncSqlConfig)
            .where(SyncSqlConfig.sync_enabled == True)
            .order_by(SyncSqlConfig.sync_priority.asc())
        )
        return result.scalars().all()

    def _parse_interval(self, interval: str) -> timedelta:
        """解析同步间隔字符串为timedelta"""
        interval = interval.lower()
        if interval.endswith('h'):
            return timedelta(hours=int(interval[:-1]))
        elif interval.endswith('d'):
            return timedelta(days=int(interval[:-1]))
        elif interval.endswith('w'):
            return timedelta(weeks=int(interval[:-1]))
        else:
            # 默认1小时
            return timedelta(hours=1)

    def _is_in_time_window(self, time_window: Optional[str]) -> bool:
        """检查当前时间是否在时间窗口内"""
        if not time_window:
            return True  # 无时间窗口限制
        
        try:
            # 解析时间窗口，格式: "02:00-04:00"
            start_str, end_str = time_window.split('-')
            start_time = datetime.strptime(start_str.strip(), '%H:%M').time()
            end_time = datetime.strptime(end_str.strip(), '%H:%M').time()
            now = datetime.now().time()
            
            if start_time <= end_time:
                # 同一天内
                return start_time <= now <= end_time
            else:
                # 跨天，如 22:00-02:00
                return now >= start_time or now <= end_time
        except Exception as e:
            logger.warning(f"时间窗口解析失败: {time_window}, 错误: {e}")
            return True  # 解析失败时默认允许执行

    async def _should_sync(self, db: AsyncSession, config: SyncSqlConfig) -> bool:
        """判断是否应该执行同步"""
        # Reload config in current session to avoid expired attributes
        result = await db.execute(
            select(SyncSqlConfig).where(SyncSqlConfig.id == config.id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return False

        # 检查时间窗口
        if not self._is_in_time_window(config.sync_time_window):
            return False

        # 检查是否到达同步时间
        if config.next_sync_time:
            return datetime.now() >= config.next_sync_time

        # 如果没有next_sync_time，说明首次执行
        return True

    def _calculate_next_sync_time(self, config: SyncSqlConfig) -> datetime:
        """计算下次同步时间"""
        interval = self._parse_interval(config.sync_interval)
        base_time = config.last_sync_time if config.last_sync_time else datetime.now()
        return base_time + interval

    async def _update_sync_status(
        self, 
        db: AsyncSession, 
        config: SyncSqlConfig, 
        status: str, 
        message: str = ""
    ):
        """更新同步状态"""
        config.last_sync_status = status
        config.last_sync_message = message
        if status == "success":
            config.last_sync_time = datetime.now()
            config.next_sync_time = self._calculate_next_sync_time(config)
        await db.flush()

    async def _run_single_sync(
        self, 
        db: AsyncSession, 
        config: SyncSqlConfig, 
        service: ERPSyncService
    ):
        """执行单个同步任务"""
        sync_type = config.sync_type
        logger.info(f"[同步任务] 开始执行: {sync_type} - {config.description or ''}")
        
        # 创建 SyncLog
        task_id = str(uuid.uuid4())
        sync_log = SyncLog(
            task_id=task_id,
            sync_type=sync_type,
            trigger_mode="scheduled",
            status="running",
            started_at=datetime.now(),
        )
        db.add(sync_log)
        
        try:
            # 更新状态为运行中
            await self._update_sync_status(db, config, "running", "同步任务开始")
            await db.flush()
            
            # 根据同步策略计算since时间
            since = None
            if config.sync_strategy == "incremental":
                if config.last_sync_time:
                    since = config.last_sync_time
                else:
                    since = datetime.now() - timedelta(days=30)
            elif config.sync_strategy == "full":
                since = None
            elif config.sync_strategy == "hybrid":
                if not config.last_sync_time:
                    since = None
                elif (datetime.now() - config.last_sync_time).days >= 7:
                    since = None
                else:
                    since = config.last_sync_time
            
            # 调用对应的同步方法
            sync_method_name = self.sync_method_map.get(sync_type)
            if sync_method_name and hasattr(service, sync_method_name):
                sync_method = getattr(service, sync_method_name)
                result = await sync_method(since=since)
                
                # 记录结果
                synced_count = result.get("synced", 0)
                created_count = result.get("created", 0)
                updated_count = result.get("updated", 0)
                errors_list = result.get("errors", [])
                errors_count = len(errors_list)

                message = f"同步完成: 处理{synced_count}条, 新增{created_count}条, 更新{updated_count}条"
                if errors_count > 0:
                    message += f", 失败{errors_count}条"

                await self._update_sync_status(db, config, "success", message)

                # 更新 SyncLog
                sync_log.status = "success" if errors_count == 0 else "failed"
                sync_log.finished_at = datetime.now()
                sync_log.duration_seconds = (sync_log.finished_at - sync_log.started_at).total_seconds()
                sync_log.synced_count = synced_count
                sync_log.created_count = created_count
                sync_log.updated_count = updated_count
                sync_log.failed_count = errors_count
                sync_log.message = message
                # 同步方法内部捕获的异常只进入了 stats["errors"]，
                # 不会触发下方外层 except。这里把错误明细写入 error_detail，
                # 否则前端只能看到 "失败N条" 而无法定位失败原因。
                if errors_list:
                    sync_log.error_detail = "\n".join(errors_list[:50])

                logger.info(f"[同步任务] {sync_type} - {message}")
            else:
                message = f"暂不支持 {sync_type} 的同步方法"
                await self._update_sync_status(db, config, "failed", message)
                sync_log.status = "failed"
                sync_log.finished_at = datetime.now()
                sync_log.duration_seconds = (sync_log.finished_at - sync_log.started_at).total_seconds()
                sync_log.message = message
                logger.warning(f"[同步任务] {sync_type} - {message}")
                
        except Exception as e:
            error_msg = f"同步失败: {str(e)}"
            try:
                await self._update_sync_status(db, config, "failed", error_msg)
            except Exception:
                logger.error(f"[同步任务] 更新同步状态失败，忽略", exc_info=True)
            try:
                sync_log.status = "failed"
                sync_log.finished_at = datetime.now()
                sync_log.duration_seconds = (sync_log.finished_at - sync_log.started_at).total_seconds()
                sync_log.message = error_msg
                sync_log.error_detail = traceback.format_exc()
            except Exception:
                pass
            logger.error(f"[同步任务] {sync_type} - {error_msg}")

    async def _run_sync(self):
        """执行一次调度循环"""
        logger.info(f"[调度器] 检查同步任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            async with AsyncSessionLocal() as db:
                configs = await self._load_sync_configs(db)
                
                for config in configs:
                    if await self._should_sync(db, config):
                        # 为每个同步任务创建独立的 session，
                        # 避免 ERPSyncService 内部 rollback 导致调度器 session 中的
                        # SyncSqlConfig 对象过期，从而引发 MissingGreenlet 错误
                        async with AsyncSessionLocal() as sync_db:
                            service = ERPSyncService(sync_db)
                            await self._run_single_sync(db, config, service)
                            # 提交同步数据（orders, materials 等）
                            try:
                                await sync_db.commit()
                            except Exception as commit_err:
                                logger.error(f"[调度器] 同步数据 commit 失败: {commit_err}")
                                await sync_db.rollback()
                        # 提交调度器状态（SyncLog, SyncSqlConfig 状态更新）
                        try:
                            await db.commit()
                        except Exception as commit_err:
                            logger.error(f"[调度器] 状态 commit 失败: {commit_err}")
                            await db.rollback()
                
                logger.info(f"[调度器] 同步任务检查完成")
                
        except Exception as e:
            try:
                logger.error(f"[调度器] 同步任务执行失败 - {e}", exc_info=True)
            except Exception:
                pass

    async def _loop(self):
        """调度循环：每分钟检查一次"""
        while self.running:
            try:
                await self._run_sync()
            except asyncio.CancelledError:
                logger.info("[调度器] 收到取消信号，退出循环")
                break
            except Exception as e:
                logger.error(f"[调度器] 同步循环异常，将继续运行: {e}", exc_info=True)
            await asyncio.sleep(60)  # 每分钟检查一次

    def start(self):
        """启动调度器"""
        if not settings.ERP_SYNC_ENABLED:
            logger.info("[调度器] ERP 同步未启用，跳过调度器启动")
            return

        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info("[调度器] 已启动，每分钟检查同步任务")

    def stop(self):
        """停止调度器"""
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("[调度器] 已停止")


# 全局调度器实例
scheduler = SyncScheduler()
