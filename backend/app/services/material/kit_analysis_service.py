"""物料齐套中心 — 齐套分析服务"""

from datetime import date
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.material.purchase_order import PurchaseOrder
from app.models.order.sale_order import SaleOrder
from app.schemas.material.schemas import KitAnalysisItem, KitAnalysisMaterialItem


def _material_status(row: PurchaseOrder) -> str:
    if row.inspection_date:
        return 'inspected'
    if row.actual_arrival_date or (row.received_qty and row.received_qty > 0):
        return 'arrived'
    if row.eta and row.eta < date.today():
        return 'overdue'
    return 'pending'


def _kit_risk_level(kit_rate: float) -> str:
    if kit_rate >= 1.0:
        return 'green'
    if kit_rate >= 0.8:
        return 'yellow'
    return 'red'


KIT_SORT_KEYS = {
    'order_no', 'kit_rate', 'total_materials', 'received_materials',
    'inspected_materials', 'pending_inspection', 'stagnant_materials', 'risk_level',
}

MATERIAL_SORT_KEYS = {
    'material_code', 'material_name', 'supplier_name', 'order_qty',
    'received_qty', 'eta', 'inspection_date', 'status', 'is_stagnant',
}


async def get_kit_analysis(
    db: AsyncSession,
    order_no: Optional[str] = None,
    risk_level: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    only_pending_shipment: bool = False,
) -> dict:
    """按订单号聚合采购到料计划数据，计算齐套率（支持分页）"""
    query = select(PurchaseOrder)
    if order_no:
        query = query.where(PurchaseOrder.order_no.ilike(f'%{order_no}%'))

    # 仅显示发货未完成的订单
    if only_pending_shipment:
        pending_orders_subq = select(SaleOrder.order_no).where(SaleOrder.delivery_completed_date.is_(None)).distinct()
        query = query.where(PurchaseOrder.order_no.in_(pending_orders_subq))

    result = await db.execute(query.order_by(PurchaseOrder.order_no))
    rows = result.scalars().all()

    # 按 order_no 分组，无订单号时使用material_code作为分组key避免合并
    groups: dict[str, list[PurchaseOrder]] = {}
    for row in rows:
        key = row.order_no if row.order_no else f'NO_ORDER-{row.material_code}'
        groups.setdefault(key, []).append(row)

    # 获取订单的合同交期
    order_nos = [k for k in groups.keys() if not k.startswith('NO_ORDER-')]
    promised_dates: dict[str, date | None] = {}
    if order_nos:
        sale_order_result = await db.execute(
            select(SaleOrder.order_no, SaleOrder.promised_date)
            .where(SaleOrder.order_no.in_(order_nos))
            .distinct()
        )
        promised_dates = {row.order_no: row.promised_date for row in sale_order_result}

    items: List[KitAnalysisItem] = []
    for on, group_rows in groups.items():
        total = len(group_rows)

        # 按物料种类计算覆盖率（木桶效应）：每种物料 received_qty >= po_qty 才算满足
        def _is_material_met(r: PurchaseOrder) -> bool:
            if r.po_qty and r.po_qty > 0:
                return r.received_qty is not None and r.received_qty >= r.po_qty
            # po_qty 为空/0 时，有到料即算满足
            return r.actual_arrival_date is not None or (r.received_qty is not None and r.received_qty > 0)

        met_count = sum(1 for r in group_rows if _is_material_met(r))
        kit_rate = round(met_count / total, 4) if total > 0 else 0.0

        received = met_count
        inspected = sum(1 for r in group_rows if r.inspection_date)
        pending_insp = sum(
            1 for r in group_rows if r.actual_arrival_date and not r.inspection_date
        )

        rl = _kit_risk_level(kit_rate)
        if risk_level and rl != risk_level:
            continue

        stagnant_count = sum(
            1 for r in group_rows
            if r.received_qty is not None and r.po_qty is not None and r.received_qty > r.po_qty
        )

        items.append(KitAnalysisItem(
            order_no=on,
            total_materials=total,
            received_materials=received,
            inspected_materials=inspected,
            pending_inspection=pending_insp,
            stagnant_materials=stagnant_count,
            kit_rate=kit_rate,
            risk_level=rl,
            promised_date=promised_dates.get(on) if not on.startswith('NO_ORDER-') else None,
        ))

    if sort_by and sort_by in KIT_SORT_KEYS:
        reverse = sort_order == 'desc'
        # Use type-aware defaults: numeric fields use 0, string fields use ''
        def sort_key(x):
            val = getattr(x, sort_by, None)
            if val is None:
                if sort_by == 'kit_rate':
                    return (True, 0.0)
                return (True, '')
            return (False, val)
        items.sort(key=sort_key, reverse=reverse)
    else:
        items.sort(key=lambda x: x.kit_rate)

    total_count = len(items)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_items = items[start_idx:end_idx]

    # Calculate statistics for all items
    red_count = sum(1 for item in items if item.risk_level == 'red')
    yellow_count = sum(1 for item in items if item.risk_level == 'yellow')
    green_count = sum(1 for item in items if item.risk_level == 'green')
    avg_kit_rate = round(sum(item.kit_rate for item in items) / len(items) * 100) if items else 0

    return {
        'items': paginated_items,
        'total': total_count,
        'page': page,
        'page_size': page_size,
        'statistics': {
            'red_count': red_count,
            'yellow_count': yellow_count,
            'green_count': green_count,
            'avg_kit_rate': avg_kit_rate,
        },
    }


async def get_order_materials(
    db: AsyncSession,
    order_no: str,
    status_filter: Optional[str] = None,
    supplier_filter: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> List[KitAnalysisMaterialItem]:
    """获取指定订单的物料明细，支持筛选和排序"""
    query = select(PurchaseOrder).where(PurchaseOrder.order_no == order_no)

    if supplier_filter:
        query = query.where(PurchaseOrder.supplier_name.ilike(f'%{supplier_filter}%'))

    result = await db.execute(query)
    rows = result.scalars().all()

    material_items = [
        KitAnalysisMaterialItem(
            material_code=r.material_code,
            material_name=r.material_name,
            supplier_name=r.supplier_name,
            order_qty=float(r.po_qty) if r.po_qty else None,
            received_qty=float(r.received_qty) if r.received_qty else None,
            eta=r.eta,
            actual_arrival_date=r.actual_arrival_date,
            inspection_date=r.inspection_date,
            status=_material_status(r),
            is_stagnant=r.received_qty is not None and r.po_qty is not None and r.received_qty > r.po_qty,
            stagnant_qty=float(r.received_qty - r.po_qty) if (r.received_qty is not None and r.po_qty is not None and r.received_qty > r.po_qty) else None,
        )
        for r in rows
    ]

    # 状态筛选（支持多个状态，逗号分隔）
    if status_filter:
        status_list = [s.strip() for s in status_filter.split(',') if s.strip()]
        material_items = [m for m in material_items if m.status in status_list]

    # 排序
    if sort_by and sort_by in MATERIAL_SORT_KEYS:
        reverse = sort_order == 'desc'
        def sort_key(x):
            val = getattr(x, sort_by, None)
            if val is None:
                if sort_by in ('order_qty', 'received_qty', 'stagnant_qty'):
                    return (True, 0.0)
                return (True, '')
            return (False, val)
        material_items.sort(key=sort_key, reverse=reverse)

    return material_items
