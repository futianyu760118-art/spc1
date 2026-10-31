"""同步延迟过滤 — 排除 ERP 同步后未更新的记录

规则：如果 ERP 最后一次同步时间 (last_sync_time) 大于记录的 updated_at 时间超过 30 分钟，
说明该记录在上次同步中未被更新（ERP 端可能已删除或变更），不应展示。
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.sync_sql_config import SyncSqlConfig
from app.models.material.purchase_order import PurchaseOrder
from app.models.material.purchase_invoice import PurchaseInvoice

SYNC_DELAY_MINUTES = 30


async def get_purchase_order_sync_filters(db: AsyncSession) -> list:
    """获取采购订单同步延迟过滤条件列表

    返回 SQLAlchemy where 条件列表，可直接传入 .where(*filters)。
    如果从未同步过（无 last_sync_time），返回空列表（不过滤）。
    """
    result = await db.execute(
        select(SyncSqlConfig.last_sync_time).where(
            SyncSqlConfig.sync_type == "purchase_orders"
        )
    )
    last_sync_time = result.scalar_one_or_none()

    if last_sync_time is None:
        return []

    cutoff = last_sync_time - timedelta(minutes=SYNC_DELAY_MINUTES)
    return [PurchaseOrder.updated_at >= cutoff]


async def get_purchase_invoice_sync_filters(db: AsyncSession) -> list:
    """获取采购开票（供应商付款排程）同步延迟过滤条件列表

    返回 SQLAlchemy where 条件列表，可直接传入 .where(*filters)。
    如果从未同步过（无 last_sync_time），返回空列表（不过滤）。
    """
    result = await db.execute(
        select(SyncSqlConfig.last_sync_time).where(
            SyncSqlConfig.sync_type == "purchase_invoices"
        )
    )
    last_sync_time = result.scalar_one_or_none()

    if last_sync_time is None:
        return []

    cutoff = last_sync_time - timedelta(minutes=SYNC_DELAY_MINUTES)
    return [PurchaseInvoice.updated_at >= cutoff]
