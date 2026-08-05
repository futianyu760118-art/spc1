"""基础数据与集成中心 — 科目余额查询 API"""

import logging
from datetime import datetime
from typing import Optional, Tuple
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_or_api_key
from app.schemas.common import ResponseModel
from app.schemas.basicdata.schemas import SubjectBalanceOut, SubjectNodeOut
from app.models.basicdata.subject_balance import SubjectBalance
from app.services.basicdata.exposable_registry import exposable

router = APIRouter()
logger = logging.getLogger(__name__)


_SORTABLE = {
    "subject_code": SubjectBalance.subject_code,
    "credit_amount_month": SubjectBalance.credit_amount_month,
    "credit_amount_year": SubjectBalance.credit_amount_year,
    "fiscal_year": SubjectBalance.fiscal_year,
    "fiscal_month": SubjectBalance.fiscal_month,
    "updated_at": SubjectBalance.updated_at,
}


def _apply_sort(query, sort_by: Optional[str], sort_order: Optional[str]):
    if sort_by and sort_by in _SORTABLE:
        col = _SORTABLE[sort_by]
        if sort_order == "desc":
            return query.order_by(col.desc().nullslast())
        return query.order_by(col.asc().nullslast())
    return query.order_by(SubjectBalance.id.desc())


async def _resolve_default_period(db: AsyncSession, year: int) -> Tuple[int, int]:
    """默认期间解析 (基于已确定的 fiscal_year):
      1) 该年内 MAX(month) - 1（>=1）; 若 MAX=1 不存在 -1, 用 MAX;
      2) 该年无任何记录, 回退到 DB 最新存在年的 MAX(month) - 1 / MAX;
      3) DB 完全为空, 返回 (year, 当前服务器月).
    返回 (fiscal_year, fiscal_month).
    """
    max_month = (
        await db.execute(
            select(func.max(SubjectBalance.fiscal_month)).where(
                SubjectBalance.fiscal_year == year
            )
        )
    ).scalar()

    if max_month is not None and max_month >= 1:
        target = max_month - 1 if max_month >= 2 else max_month
        return year, target

    latest_year = (
        await db.execute(select(func.max(SubjectBalance.fiscal_year)))
    ).scalar()
    if latest_year is not None:
        max_month_latest = (
            await db.execute(
                select(func.max(SubjectBalance.fiscal_month)).where(
                    SubjectBalance.fiscal_year == latest_year
                )
            )
        ).scalar()
        if max_month_latest is not None and max_month_latest >= 1:
            target = max_month_latest - 1 if max_month_latest >= 2 else max_month_latest
            return int(latest_year), target

    return year, datetime.now().month


@router.get("", response_model=ResponseModel[dict])
@exposable(
    endpoint_code="int:finance.subject_balances.list",
    name="科目余额列表",
    description="按期间/科目/核算项目筛选科目余额列表",
    tags=["finance"],
)
async def list_subject_balances(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    fiscal_year: Optional[int] = Query(None, description="年份"),
    fiscal_month: Optional[int] = Query(None, ge=1, le=12, description="月份(1-12)"),
    subject_category: Optional[str] = Query(None, description="科目类别名称(精确)"),
    keyword: Optional[str] = Query(None, description="模糊匹配科目编码/名称"),
    item_code: Optional[str] = Query(None, description="核算项目代码(模糊)"),
    item_name: Optional[str] = Query(None, description="核算项目名称(模糊)"),
    subject_id: Optional[int] = Query(None, description="科目ID"),
    parent_subject_id: Optional[int] = Query(None, description="科目父ID"),
    credit_min: Optional[Decimal] = Query(None, description="本月贷方发生下限"),
    credit_max: Optional[Decimal] = Query(None, description="本月贷方发生上限"),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None, description="asc/desc"),
    response: Response = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
):
    used_default = False
    if fiscal_year is None:
        fiscal_year = datetime.now().year
        used_default = True
    if fiscal_month is None:
        fiscal_year, fiscal_month = await _resolve_default_period(db, fiscal_year)
        used_default = True
    if used_default and response is not None:
        response.headers["X-Default-Period"] = f"{fiscal_year}-{fiscal_month:02d}"

    query = select(SubjectBalance)
    if fiscal_year is not None:
        query = query.where(SubjectBalance.fiscal_year == fiscal_year)
    if fiscal_month is not None:
        query = query.where(SubjectBalance.fiscal_month == fiscal_month)
    if subject_category:
        query = query.where(SubjectBalance.subject_category == subject_category)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(
            SubjectBalance.subject_code.ilike(like),
            SubjectBalance.subject_name.ilike(like),
        ))
    if item_code:
        query = query.where(SubjectBalance.item_code.ilike(f"%{item_code}%"))
    if item_name:
        query = query.where(SubjectBalance.item_name.ilike(f"%{item_name}%"))
    if subject_id is not None:
        query = query.where(SubjectBalance.subject_id == subject_id)
    if parent_subject_id is not None:
        query = query.where(SubjectBalance.parent_subject_id == parent_subject_id)
    if credit_min is not None:
        query = query.where(SubjectBalance.credit_amount_month >= credit_min)
    if credit_max is not None:
        query = query.where(SubjectBalance.credit_amount_month <= credit_max)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = _apply_sort(query, sort_by, sort_order)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [SubjectBalanceOut.model_validate(r) for r in result.scalars().all()]
    return ResponseModel(data={"items": items, "total": total, "page": page, "page_size": page_size})


async def _build_subject_nodes(
    db: AsyncSession,
    parent_subject_id_filter: Optional[int],
    is_root: bool,
    fiscal_year: Optional[int],
    fiscal_month: Optional[int],
    subject_category: Optional[str],
    keyword: Optional[str],
    item_code: Optional[str],
    item_name: Optional[str],
) -> list:
    base = select(SubjectBalance)
    if is_root:
        base = base.where(
            SubjectBalance.parent_subject_id.is_(None)
            | (SubjectBalance.parent_subject_id == 0)
        )
    else:
        base = base.where(
            SubjectBalance.parent_subject_id == parent_subject_id_filter,
            SubjectBalance.subject_id != parent_subject_id_filter,
        )
    if fiscal_year is not None:
        base = base.where(SubjectBalance.fiscal_year == fiscal_year)
    if fiscal_month is not None:
        base = base.where(SubjectBalance.fiscal_month == fiscal_month)
    if subject_category:
        base = base.where(SubjectBalance.subject_category == subject_category)
    if keyword:
        like = f"%{keyword}%"
        base = base.where(or_(
            SubjectBalance.subject_code.ilike(like),
            SubjectBalance.subject_name.ilike(like),
        ))
    if item_code:
        base = base.where(SubjectBalance.item_code.ilike(f"%{item_code}%"))
    if item_name:
        base = base.where(SubjectBalance.item_name.ilike(f"%{item_name}%"))

    rows = (await db.execute(base)).scalars().all()
    if not rows:
        return []

    # 按 subject_id 分组聚合
    grouped: dict[int, dict] = {}
    for r in rows:
        g = grouped.setdefault(r.subject_id, {
            "subject_id": r.subject_id,
            "subject_category": r.subject_category,
            "subject_name": r.subject_name,
            "subject_code": r.subject_code,
            "parent_subject_id": r.parent_subject_id,
            "item_code": r.item_code,
            "item_name": r.item_name,
            "periods": [],
        })
        g["periods"].append((r.fiscal_year, r.fiscal_month, r.credit_amount_month, r.credit_amount_year))

    # 全表的所有 parent_subject_id,用于判断 has_children
    parent_ids_q = select(SubjectBalance.parent_subject_id).where(
        SubjectBalance.parent_subject_id.is_not(None),
        SubjectBalance.parent_subject_id != 0,
    ).distinct()
    parent_ids = set((await db.execute(parent_ids_q)).scalars().all())

    # 子科目数(同表统计 parent 计数)
    child_count_q = select(
        SubjectBalance.parent_subject_id,
        func.count(SubjectBalance.subject_id.distinct())
    ).where(
        SubjectBalance.parent_subject_id.is_not(None),
        SubjectBalance.parent_subject_id != 0,
    ).group_by(SubjectBalance.parent_subject_id)
    child_count_map = {
        pid: cnt for pid, cnt in (await db.execute(child_count_q)).all()
    }

    nodes = []
    for subject_id, g in grouped.items():
        periods = sorted(g["periods"], key=lambda p: (p[0], p[1]))
        latest_year, latest_month, latest_month_amt, latest_year_amt = periods[-1]
        period_count = len(periods)
        nodes.append(SubjectNodeOut(
            subject_id=subject_id,
            subject_category=g["subject_category"],
            subject_name=g["subject_name"],
            subject_code=g["subject_code"],
            parent_subject_id=g["parent_subject_id"],
            item_code=g["item_code"],
            item_name=g["item_name"],
            period_count=period_count,
            has_children=subject_id in parent_ids,
            child_count=child_count_map.get(subject_id, 0),
            latest_year=latest_year,
            latest_month=latest_month,
            credit_amount_month=latest_month_amt,
            credit_amount_year=latest_year_amt,
        ))
    nodes.sort(key=lambda n: (n.subject_code or "", n.subject_name or ""))
    return nodes


@router.get("/tree/roots", response_model=ResponseModel[dict])
@exposable(
    endpoint_code="int:finance.subject_balances.roots",
    name="科目余额根节点",
    description="返回无父科目的科目节点(按科目聚合,最新期间余额)",
    tags=["finance"],
)
async def list_subject_balance_roots(
    fiscal_year: Optional[int] = Query(None, description="年份"),
    fiscal_month: Optional[int] = Query(None, ge=1, le=12, description="月份(1-12)"),
    subject_category: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    item_code: Optional[str] = Query(None),
    item_name: Optional[str] = Query(None),
    response: Response = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
):
    used_default = False
    if fiscal_year is None:
        fiscal_year = datetime.now().year
        used_default = True
    if fiscal_month is None:
        fiscal_year, fiscal_month = await _resolve_default_period(db, fiscal_year)
        used_default = True
    if used_default and response is not None:
        response.headers["X-Default-Period"] = f"{fiscal_year}-{fiscal_month:02d}"
    nodes = await _build_subject_nodes(
        db, None, True, fiscal_year, fiscal_month,
        subject_category, keyword, item_code, item_name,
    )
    return ResponseModel(data={"items": [n.model_dump() for n in nodes], "total": len(nodes)})


@router.get("/tree/children/{parent_subject_id}", response_model=ResponseModel[dict])
@exposable(
    endpoint_code="int:finance.subject_balances.children",
    name="科目余额子节点",
    description="返回指定父科目下的子科目节点",
    tags=["finance"],
)
async def list_subject_balance_children(
    parent_subject_id: int,
    fiscal_year: Optional[int] = Query(None),
    fiscal_month: Optional[int] = Query(None, ge=1, le=12),
    subject_category: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    item_code: Optional[str] = Query(None),
    item_name: Optional[str] = Query(None),
    response: Response = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
):
    used_default = False
    if fiscal_year is None:
        fiscal_year = datetime.now().year
        used_default = True
    if fiscal_month is None:
        fiscal_year, fiscal_month = await _resolve_default_period(db, fiscal_year)
        used_default = True
    if used_default and response is not None:
        response.headers["X-Default-Period"] = f"{fiscal_year}-{fiscal_month:02d}"
    nodes = await _build_subject_nodes(
        db, parent_subject_id, False, fiscal_year, fiscal_month,
        subject_category, keyword, item_code, item_name,
    )
    return ResponseModel(data={"items": [n.model_dump() for n in nodes], "total": len(nodes)})


@router.get("/{balance_id}", response_model=ResponseModel[SubjectBalanceOut])
@exposable(
    endpoint_code="int:finance.subject_balances.detail",
    name="科目余额详情",
    description="按主键ID获取单条科目余额记录",
    tags=["finance"],
)
async def get_subject_balance(
    balance_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
):
    result = await db.execute(select(SubjectBalance).where(SubjectBalance.id == balance_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="科目余额记录不存在")
    return ResponseModel(data=SubjectBalanceOut.model_validate(item))
