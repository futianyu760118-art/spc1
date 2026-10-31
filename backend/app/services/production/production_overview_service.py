"""生产协同中心 — 生产总览聚合服务"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct

from app.models.production.process_progress import ProcessProgress
from app.models.production.process_exception import ProcessException
from app.schemas.production.schemas import (
    ProcessTypeStatItem, ProductProcessItem, OrderProcessItem, ProductionOverviewData,
)

PROCESS_TYPE_LABELS = {
    'front_process': '前道',
    'smt': '贴片',
    'lean': '精益',
    'assembly': '组装',
    'packaging': '包装',
}

PROCESS_ORDER = ['front_process', 'smt', 'lean', 'assembly', 'packaging']

# 严重程度排序: overdue/abnormal > pending > completed > None
_SEVERITY = {'overdue': 3, 'abnormal': 3, 'pending': 2, 'completed': 1}


def _worse_status(a, b):
    """返回更严重的状态"""
    sa = _SEVERITY.get(a, 0)
    sb = _SEVERITY.get(b, 0)
    return a if sa >= sb else b


def _detect_block(status_map: dict):
    """按工序顺序检测卡点，返回 (current_process, block_reason)"""
    for pt in PROCESS_ORDER:
        s = status_map.get(pt)
        if s in ('overdue', 'abnormal'):
            return pt, f"{PROCESS_TYPE_LABELS.get(pt, pt)}工序异常/逾期"
        if s == 'pending':
            return pt, None
        if s is None:
            return pt, f"未进入{PROCESS_TYPE_LABELS.get(pt, pt)}工序"
    return None, None


async def get_production_overview(db: AsyncSession) -> ProductionOverviewData:
    """获取生产总览：各工序统计 + 按订单→产品两级聚合工序状态"""

    # 1. 各工序统计
    process_stats = []
    for pt in PROCESS_ORDER:
        total_result = await db.execute(
            select(func.count(ProcessProgress.id)).where(ProcessProgress.process_type == pt)
        )
        total = total_result.scalar() or 0

        completed_result = await db.execute(
            select(func.count(ProcessProgress.id)).where(
                ProcessProgress.process_type == pt,
                ProcessProgress.status == 'completed',
            )
        )
        completed = completed_result.scalar() or 0

        in_progress_result = await db.execute(
            select(func.count(ProcessProgress.id)).where(
                ProcessProgress.process_type == pt,
                ProcessProgress.status == 'pending',
            )
        )
        in_progress = in_progress_result.scalar() or 0

        overdue_result = await db.execute(
            select(func.count(ProcessProgress.id)).where(
                ProcessProgress.process_type == pt,
                ProcessProgress.status == 'overdue',
            )
        )
        overdue = overdue_result.scalar() or 0

        abnormal_result = await db.execute(
            select(func.count(ProcessProgress.id)).where(
                ProcessProgress.process_type == pt,
                ProcessProgress.status == 'abnormal',
            )
        )
        abnormal = abnormal_result.scalar() or 0

        process_stats.append(ProcessTypeStatItem(
            process_type=pt,
            total=total,
            completed=completed,
            in_progress=in_progress,
            overdue=overdue,
            abnormal=abnormal,
        ))

    # 2. 按订单→产品两级聚合
    order_nos_result = await db.execute(
        select(distinct(ProcessProgress.order_no)).where(ProcessProgress.order_no.isnot(None))
    )
    order_nos = [r for r in order_nos_result.scalars().all() if r]

    orders = []
    blocked = 0
    for order_no in order_nos:
        # 获取该订单下所有不同的 product_code
        pc_result = await db.execute(
            select(distinct(ProcessProgress.product_code)).where(
                ProcessProgress.order_no == order_no,
            )
        )
        product_codes = [r for r in pc_result.scalars().all() if r]
        # 如果没有 product_code，用 None 作为一组（兼容旧数据）
        if not product_codes:
            product_codes = [None]

        products = []
        order_worst_process = None
        order_worst_reason = None
        order_worst_severity = 0

        for pc in product_codes:
            status_map = {}
            model_code = None
            color_spec = None
            qty = None

            for pt in PROCESS_ORDER:
                filters = [
                    ProcessProgress.process_type == pt,
                    ProcessProgress.order_no == order_no,
                ]
                if pc is not None:
                    filters.append(ProcessProgress.product_code == pc)

                result = await db.execute(
                    select(ProcessProgress)
                    .where(*filters)
                    .order_by(ProcessProgress.plan_date.desc().nullslast(), ProcessProgress.id.desc())
                    .limit(1)
                )
                rec = result.scalar_one_or_none()
                if rec:
                    status_map[pt] = rec.status
                    if not model_code:
                        model_code = rec.model_code
                    if not color_spec:
                        color_spec = rec.color_spec
                    if not qty:
                        qty = rec.qty
                else:
                    status_map[pt] = None

            current_process, block_reason = _detect_block(status_map)
            sev = _SEVERITY.get(status_map.get(current_process, ''), 0) if current_process else 0

            products.append(ProductProcessItem(
                product_code=pc,
                model_code=model_code,
                color_spec=color_spec,
                qty=qty,
                front_process_status=status_map.get('front_process'),
                smt_status=status_map.get('smt'),
                lean_status=status_map.get('lean'),
                assembly_status=status_map.get('assembly'),
                packaging_status=status_map.get('packaging'),
                current_process=current_process,
                block_reason=block_reason,
            ))

            # 订单级取最严重产品的卡点
            if sev > order_worst_severity:
                order_worst_severity = sev
                order_worst_process = current_process
                order_worst_reason = block_reason

        if order_worst_reason:
            blocked += 1

        orders.append(OrderProcessItem(
            order_no=order_no,
            products=products,
            current_process=order_worst_process,
            block_reason=order_worst_reason,
        ))

    return ProductionOverviewData(
        process_stats=process_stats,
        orders=orders,
        total_orders=len(orders),
        blocked_orders=blocked,
    )
