"""物料齐套中心 — 长交期物料池分析服务（从采购到料计划派生）"""

from datetime import date
from typing import Optional, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, literal, Numeric

from app.models.material.purchase_order import PurchaseOrder
from app.models.material.long_lead_material import LongLeadMaterial
from app.schemas.material.schemas import LongLeadDerivedItem


# 长交期阈值（天）
LEAD_TIME_THRESHOLD = 20


def _risk_level(avg_days: Optional[float]) -> str:
    if avg_days is None:
        return 'normal'
    if avg_days >= 30:
        return 'danger'
    if avg_days >= LEAD_TIME_THRESHOLD:
        return 'warning'
    return 'normal'


LONG_LEAD_SORT_KEYS = {
    'material_code', 'material_name', 'supplier_name',
    'avg_lead_time_days', 'max_lead_time_days', 'po_count', 'latest_eta',
    'risk_level', 'status',
}


async def get_long_lead_pool(
    db: AsyncSession,
    keyword: Optional[str] = None,
    supplier_name: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Tuple[List[LongLeadDerivedItem], int, dict]:
    """从采购到料计划聚合派生长交期物料池

    1. 查询有 actual_arrival_date 和 po_date 的 PurchaseOrder
    2. 按 material_code + supplier_name 聚合计算平均/最大交期
    3. 筛选 avg_lead_time >= LEAD_TIME_THRESHOLD
    4. LEFT JOIN long_lead_material 获取 improvement_plan / status
    5. 返回分页结果和全局统计
    """
    # 计算交期天数: PG中 date - date 直接返回 integer 天数
    lead_days_expr = PurchaseOrder.actual_arrival_date - PurchaseOrder.po_date

    # 聚合查询（cast to Numeric 避免整数除法问题）
    avg_lead = func.avg(lead_days_expr.cast(Numeric)).label('avg_lead_time_days')
    max_lead = func.max(lead_days_expr).label('max_lead_time_days')
    po_count = func.count(PurchaseOrder.id).label('po_count')
    latest_eta = func.max(PurchaseOrder.eta).label('latest_eta')
    # 取最新的 material_name
    latest_material_name = func.max(PurchaseOrder.material_name).label('material_name')

    group_cols = [PurchaseOrder.material_code, PurchaseOrder.supplier_name]

    agg_query = (
        select(
            *group_cols,
            avg_lead,
            max_lead,
            po_count,
            latest_eta,
            latest_material_name,
        )
        .where(
            PurchaseOrder.actual_arrival_date.isnot(None),
            PurchaseOrder.po_date.isnot(None),
        )
        .group_by(*group_cols)
        .having(avg_lead >= LEAD_TIME_THRESHOLD)
    )

    # 关键词筛选（在聚合前过滤）
    if keyword:
        like = f'%{keyword}%'
        agg_query = agg_query.where(
            PurchaseOrder.material_code.ilike(like)
            | PurchaseOrder.material_name.ilike(like)
            | PurchaseOrder.supplier_name.ilike(like)
        )
    if supplier_name:
        agg_query = agg_query.where(
            PurchaseOrder.supplier_name.ilike(f'%{supplier_name}%')
        )

    # 执行聚合查询
    agg_result = await db.execute(agg_query)
    agg_rows = agg_result.all()

    # 加载所有注解记录
    annotations_result = await db.execute(select(LongLeadMaterial))
    annotations_map: dict[tuple, LongLeadMaterial] = {}
    for ann in annotations_result.scalars().all():
        key = (ann.material_code or '', ann.supplier_name or '')
        annotations_map[key] = ann

    # 组装结果
    items: List[LongLeadDerivedItem] = []
    for row in agg_rows:
        material_code = row.material_code or ''
        supplier = row.supplier_name or ''
        avg_days = float(row.avg_lead_time_days) if row.avg_lead_time_days else None
        max_days = int(row.max_lead_time_days) if row.max_lead_time_days else None
        rl = _risk_level(avg_days)

        # 风险等级筛选
        if risk_level and rl != risk_level:
            continue

        # 查找注解
        ann_key = (material_code, supplier)
        annotation = annotations_map.get(ann_key)

        # 状态筛选
        ann_status = annotation.status if annotation else 'active'
        if status and ann_status != status:
            continue

        items.append(LongLeadDerivedItem(
            id=annotation.id if annotation else None,
            material_code=material_code,
            material_name=row.material_name,
            supplier_name=supplier,
            avg_lead_time_days=round(avg_days, 1) if avg_days else None,
            max_lead_time_days=max_days,
            po_count=row.po_count,
            latest_eta=row.latest_eta,
            improvement_plan=annotation.improvement_plan if annotation else None,
            status=ann_status,
            risk_level=rl,
        ))

    # 排序
    if sort_by and sort_by in LONG_LEAD_SORT_KEYS:
        reverse = sort_order == 'desc'
        items.sort(key=lambda x: (getattr(x, sort_by, None) is None, getattr(x, sort_by, None) or ''), reverse=reverse)
    else:
        items.sort(key=lambda x: x.avg_lead_time_days or 0, reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    # 计算全局统计（不受筛选影响）
    global_stats = {
        'total': len(items),
        'active_count': sum(1 for item in items if item.status == 'active'),
        'danger_count': sum(1 for item in items if item.risk_level == 'danger'),
        'warning_count': sum(1 for item in items if item.risk_level == 'warning'),
    }

    return page_items, total, global_stats


async def scan_and_create_annotations(db: AsyncSession) -> dict:
    """扫描采购到料计划，为满足长交期条件但无注解记录的物料自动创建注解"""
    lead_days_expr = PurchaseOrder.actual_arrival_date - PurchaseOrder.po_date
    avg_lead = func.avg(lead_days_expr.cast(Numeric)).label('avg_lead_time_days')

    group_cols = [PurchaseOrder.material_code, PurchaseOrder.supplier_name]

    agg_query = (
        select(*group_cols, avg_lead)
        .where(
            PurchaseOrder.actual_arrival_date.isnot(None),
            PurchaseOrder.po_date.isnot(None),
        )
        .group_by(*group_cols)
        .having(avg_lead >= LEAD_TIME_THRESHOLD)
    )

    agg_result = await db.execute(agg_query)
    agg_rows = agg_result.all()

    # 已有注解
    existing_result = await db.execute(select(LongLeadMaterial))
    existing_keys = {
        (ann.material_code or '', ann.supplier_name or '')
        for ann in existing_result.scalars().all()
    }

    created = 0
    for row in agg_rows:
        key = (row.material_code or '', row.supplier_name or '')
        if key in existing_keys:
            continue
        ann = LongLeadMaterial(
            material_code=key[0],
            supplier_name=key[1],
            improvement_plan=None,
            status='active',
        )
        db.add(ann)
        created += 1

    await db.flush()
    return {'new_annotations': created}
