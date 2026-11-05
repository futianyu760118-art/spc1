"""MRP 数据质量检查：K3 同步新鲜度。

SPC 的 MRP 输入全部来自 K3，任何关键同步任务失败或长时间未更新，
都会让运算结果失真。本模块只负责识别并返回问题，是否阻断由调用方决定。
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.sync_sql_config import SyncSqlConfig

# 关键同步类型 → 允许的最大数据年龄（小时）
KEY_SYNC_MAX_AGE_HOURS = {
    "orders": 24,
    "order_details": 24,
    "materials_masterdata": 48,
    "boms": 48,
    "bom_details": 48,
    "inventory": 24,
    "purchase_orders": 24,
    "production_task_orders": 24,
    "subcontract_orders": 24,
    "subcontract_order_details": 24,
    "transfer_orders": 24,
    "mrp_plan_orders": 24,
}


async def check_sync_freshness(
    db: AsyncSession, now: Optional[datetime] = None
) -> list[dict]:
    """检查关键同步任务的状态与新鲜度，返回问题清单。"""
    current = now or datetime.now()
    rows = (
        await db.execute(
            select(
                SyncSqlConfig.sync_type,
                SyncSqlConfig.sync_enabled,
                SyncSqlConfig.last_sync_status,
                SyncSqlConfig.last_sync_time,
            ).where(SyncSqlConfig.sync_type.in_(list(KEY_SYNC_MAX_AGE_HOURS)))
        )
    ).all()

    issues: list[dict] = []
    configured_types = {row[0] for row in rows}
    for sync_type in KEY_SYNC_MAX_AGE_HOURS:
        if sync_type not in configured_types:
            issues.append(
                {
                    "sync_type": sync_type,
                    "reason": "not_configured",
                    "last_sync_time": None,
                    "max_age_hours": KEY_SYNC_MAX_AGE_HOURS[sync_type],
                }
            )
    for sync_type, enabled, status, last_sync_time in rows:
        max_age = KEY_SYNC_MAX_AGE_HOURS[sync_type]
        if not enabled:
            issues.append(
                {
                    "sync_type": sync_type,
                    "reason": "disabled",
                    "last_sync_time": _iso(last_sync_time),
                    "max_age_hours": max_age,
                }
            )
            continue
        if last_sync_time is None:
            issues.append(
                {
                    "sync_type": sync_type,
                    "reason": "never_synced",
                    "last_sync_time": None,
                    "max_age_hours": max_age,
                }
            )
            continue
        age = current - last_sync_time
        if age > timedelta(hours=max_age):
            issues.append(
                {
                    "sync_type": sync_type,
                    "reason": "stale",
                    "last_sync_time": _iso(last_sync_time),
                    "age_hours": round(age.total_seconds() / 3600, 1),
                    "max_age_hours": max_age,
                }
            )
            continue
        if status != "success":
            issues.append(
                {
                    "sync_type": sync_type,
                    "reason": f"status_{status or 'unknown'}",
                    "last_sync_time": _iso(last_sync_time),
                    "max_age_hours": max_age,
                }
            )
    return issues


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None
