"""OA 返工单查询 / 同步 API（供日期调整页选单插入）."""

from collections import defaultdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.order.sale_order import SaleOrderLine
from app.models.production.rework_order import ProductionReworkOrder
from app.models.production.schedule_plan import ProductionSchedulePlan
from app.schemas.common import PageResult, ResponseModel
from app.schemas.production.schemas import ReworkOrderOut
from app.services.production.rework_order_sync_service import sync_rework_orders

router = APIRouter()


def _normalize(value: Optional[str]) -> str:
    return str(value or "").strip().upper()


async def _resolve_line_numbers(
    db: AsyncSession,
    rows: list[ProductionReworkOrder],
) -> dict[str, tuple[str, str]]:
    """按订单号+产品编码自动匹配行号.

    优先订单行（sale_order_line），其次现有排产计划（production_schedule_plan）；
    完全匹配不到时才回退到 1。
    返回 {request_id: (line_no, source)}
    """
    order_nos = {str(row.order_no).strip() for row in rows if row.order_no}
    if not order_nos:
        return {}

    exact_order: dict[tuple[str, str], str] = {}
    lines_by_order: dict[str, set[str]] = defaultdict(set)
    order_rows = (
        await db.execute(
            select(
                SaleOrderLine.order_no,
                SaleOrderLine.line_no,
                SaleOrderLine.product_code,
            ).where(SaleOrderLine.order_no.in_(order_nos))
        )
    ).all()
    for order_no, line_no, product_code in order_rows:
        order_key = str(order_no).strip()
        line_key = str(line_no).strip()
        exact_order[(order_key, _normalize(product_code))] = line_key
        lines_by_order[order_key].add(line_key)

    exact_plan: dict[tuple[str, str], str] = {}
    lines_by_plan: dict[str, set[str]] = defaultdict(set)
    plan_rows = (
        await db.execute(
            select(
                ProductionSchedulePlan.order_no,
                ProductionSchedulePlan.line_no,
                ProductionSchedulePlan.product_code,
            ).where(
                ProductionSchedulePlan.order_no.in_(order_nos),
                ProductionSchedulePlan.is_active == True,
            )
        )
    ).all()
    for order_no, line_no, product_code in plan_rows:
        order_key = str(order_no).strip()
        line_key = str(line_no).strip()
        exact_plan.setdefault((order_key, _normalize(product_code)), line_key)
        lines_by_plan[order_key].add(line_key)

    resolved: dict[str, tuple[str, str]] = {}
    for row in rows:
        order_key = str(row.order_no or "").strip()
        product_key = _normalize(row.product_code)
        if not order_key:
            resolved[row.request_id] = ("1", "default")
            continue
        line = exact_order.get((order_key, product_key))
        if line:
            resolved[row.request_id] = (line, "order")
            continue
        order_lines = lines_by_order.get(order_key) or set()
        if len(order_lines) == 1:
            resolved[row.request_id] = (next(iter(order_lines)), "order_unique")
            continue
        line = exact_plan.get((order_key, product_key))
        if line:
            resolved[row.request_id] = (line, "plan")
            continue
        plan_lines = lines_by_plan.get(order_key) or set()
        if len(plan_lines) == 1:
            resolved[row.request_id] = (next(iter(plan_lines)), "plan_unique")
            continue
        resolved[row.request_id] = ("1", "default")
    return resolved


@router.get("", response_model=ResponseModel[PageResult[ReworkOrderOut]])
async def list_rework_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    only_with_hours: bool = Query(False),
    current_user: dict = Depends(PermissionChecker("production.schedule_date_adjust", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(or_(
            ProductionReworkOrder.order_no.ilike(like),
            ProductionReworkOrder.product_code.ilike(like),
            ProductionReworkOrder.product_name.ilike(like),
            ProductionReworkOrder.flow_no.ilike(like),
            ProductionReworkOrder.title.ilike(like),
        ))
    if order_no:
        conditions.append(ProductionReworkOrder.order_no == order_no)
    if product_code:
        conditions.append(ProductionReworkOrder.product_code == product_code)
    if date_start:
        conditions.append(ProductionReworkOrder.apply_date >= date_start)
    if date_end:
        conditions.append(ProductionReworkOrder.apply_date <= date_end)
    if only_with_hours:
        conditions.append(ProductionReworkOrder.rework_hours > 0)

    count_stmt = select(func.count()).select_from(ProductionReworkOrder)
    list_stmt = select(ProductionReworkOrder)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        list_stmt = list_stmt.where(*conditions)

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (
        await db.execute(
            list_stmt.order_by(
                ProductionReworkOrder.apply_date.desc(),
                ProductionReworkOrder.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    line_map = await _resolve_line_numbers(db, list(rows))
    items = []
    for row in rows:
        line_no, line_source = line_map.get(row.request_id, ("1", "default"))
        items.append(
            ReworkOrderOut.model_validate(row).model_copy(update={
                "line_no": line_no,
                "line_no_source": line_source,
            })
        )
    return ResponseModel(data=PageResult(
        total=total, page=page, page_size=page_size, items=items,
    ))


@router.post("/sync", response_model=ResponseModel[dict])
async def sync_oa_rework_orders(
    current_user: dict = Depends(PermissionChecker("production.schedule_date_adjust", "update")),
    db: AsyncSession = Depends(get_db),
):
    stats = await sync_rework_orders(db)
    await db.commit()
    return ResponseModel(data=stats)
