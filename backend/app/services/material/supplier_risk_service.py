"""物料齐套中心 — 供应商风险分析服务"""

from datetime import date
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.material.purchase_order import PurchaseOrder
from app.models.material.material_issue import MaterialIssue
from app.schemas.material.schemas import SupplierRiskItem, SupplierRiskOrderItem


def _supplier_risk_level(delayed_count: int, issue_count: int, avg_delay: float) -> str:
    if delayed_count >= 5 or avg_delay >= 7 or issue_count >= 3:
        return 'red'
    if delayed_count >= 2 or avg_delay >= 3 or issue_count >= 1:
        return 'yellow'
    return 'green'


SUPPLIER_RISK_SORT_KEYS = {
    'supplier_name', 'total_orders', 'delayed_count', 'issue_count',
    'avg_delay_days', 'risk_level',
}


async def get_supplier_risk(
    db: AsyncSession,
    supplier: Optional[str] = None,
    exact_supplier: bool = False,
    risk_level: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> List[SupplierRiskItem]:
    """按供应商聚合采购到料计划数据，计算延期/质量风险"""

    # 查询采购到料计划（已有到料时间和ETA的记录）
    po_query = select(PurchaseOrder).where(
        PurchaseOrder.supplier_name.isnot(None),
    )
    if supplier:
        if exact_supplier:
            po_query = po_query.where(PurchaseOrder.supplier_name == supplier)
        else:
            po_query = po_query.where(PurchaseOrder.supplier_name.ilike(f'%{supplier}%'))

    po_result = await db.execute(po_query)
    pos = po_result.scalars().all()

    # 问题物料统计暂时禁用，因为问题物料表没有供应商字段
    # 如果需要统计供应商质量问题，需要在问题物料表增加supplier_name字段
    # issue_count_map: dict[str, int] = {}

    # 按供应商分组
    groups: dict[str, list[PurchaseOrder]] = {}
    for po in pos:
        key = (po.supplier_name or '').strip()
        if key:
            groups.setdefault(key, []).append(po)

    today = date.today()
    items: List[SupplierRiskItem] = []

    for sup_name, group_rows in groups.items():
        total_orders = len(group_rows)
        delayed = []
        for r in group_rows:
            if r.actual_arrival_date and r.eta and r.actual_arrival_date > r.eta:
                delayed.append((r.actual_arrival_date - r.eta).days)
            elif not r.actual_arrival_date and r.eta and r.eta < today:
                delayed.append((today - r.eta).days)

        delayed_count = len(delayed)
        avg_delay = round(sum(delayed) / len(delayed), 1) if delayed else 0.0
        sup_issue_count = 0  # 暂时设为0，待问题物料表增加supplier_name字段后再统计

        rl = _supplier_risk_level(delayed_count, sup_issue_count, avg_delay)
        if risk_level and rl != risk_level:
            continue

        # 构建订单列表
        order_items = [
            SupplierRiskOrderItem(
                po_no=r.po_no,
                material_code=r.material_code,
                material_name=r.material_name,
                order_no=r.order_no,
                eta=r.eta,
                actual_arrival_date=r.actual_arrival_date,
                inspection_date=r.inspection_date,
                po_status=r.po_status,
                po_qty=r.po_qty,
                received_qty=r.received_qty,
            )
            for r in group_rows
        ]

        items.append(SupplierRiskItem(
            supplier_name=sup_name,
            total_orders=total_orders,
            delayed_count=delayed_count,
            issue_count=sup_issue_count,
            avg_delay_days=avg_delay,
            risk_level=rl,
            orders=order_items,
        ))

    if sort_by and sort_by in SUPPLIER_RISK_SORT_KEYS:
        reverse = sort_order == 'desc'
        numeric_keys = {'total_orders', 'delayed_count', 'issue_count', 'avg_delay_days'}

        def _sort_key(x):
            v = getattr(x, sort_by, None)
            if v is None:
                return (1, 0 if sort_by in numeric_keys else '')
            return (0, v)

        items.sort(key=_sort_key, reverse=reverse)
    else:
        items.sort(key=lambda x: (-x.delayed_count, -x.avg_delay_days))
    return items
