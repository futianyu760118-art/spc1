"""订单交付中心 — 采购订单 ETA 更新服务（ETA 端点与 MRP 例外改期共用）。"""

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.eta_update import ETAUpdate


async def update_purchase_order_eta(
    db: AsyncSession,
    *,
    po_no: Optional[str] = None,
    new_eta: date,
    updater: str,
    update_reason: Optional[str] = None,
    remark: Optional[str] = None,
    po_id: Optional[int] = None,
    detail_id: Optional[int] = None,
) -> PurchaseOrder:
    """更新采购订单 ETA 并写入变更历史与审计日志；不 commit，由调用方会话统一提交。

    定位优先 po_id（主键，MRP 例外改期用），否则 po_no（可加 detail_id 过滤明细行）；
    PO 不存在时抛 ValueError("PO不存在")，由端点转换为 404。
    """
    if po_id is not None:
        stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id)
    else:
        stmt = select(PurchaseOrder).where(PurchaseOrder.po_no == po_no)
        if detail_id is not None:
            stmt = stmt.where(PurchaseOrder.detail_id == detail_id)
    po = (await db.execute(stmt)).scalar_one_or_none()
    if not po:
        raise ValueError("PO不存在")

    old_eta = po.eta
    po.eta = new_eta

    db.add(ETAUpdate(
        po_no=po.po_no,
        old_eta=old_eta,
        new_eta=new_eta,
        updater=updater,
        update_reason=update_reason,
        remark=remark,
    ))

    await log_audit(
        db, "purchase_order", po.id, "update",
        field_name="eta", old_value=str(old_eta) if old_eta else None,
        new_value=str(new_eta), operator=updater,
    )
    return po
