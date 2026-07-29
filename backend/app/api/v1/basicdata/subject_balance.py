"""基础数据与集成中心 — 科目余额查询 API"""

import logging
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_or_api_key
from app.schemas.common import ResponseModel
from app.schemas.basicdata.schemas import SubjectBalanceOut
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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
):
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
