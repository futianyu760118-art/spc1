"""物料齐套中心 — 物料盘点 API (scm_inventory_check)"""

from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel, PageResult
from app.schemas.material.stock_check import (
    StockCheckCreate,
    StockCheckFromMaterialsCreate,
    StockCheckOut,
    StockCheckListOut,
    StockCheckItemOut,
    StockCheckItemUpdate,
    StockCheckItemBatchUpdate,
    CoCheckersUpdate,
    MaterialHistoryItem,
    MaterialOrderUsageOut,
    MaterialCandidateOut,
)
from app.models.material.inventory_check import StockCheck, StockCheckItem
from app.services.material.stock_check_service import (
    create_stock_check_from_order,
    create_stock_check_from_materials,
    list_material_candidates,
    update_stock_check_item,
    batch_update_items,
    complete_stock_check,
    cancel_stock_check,
    set_co_checkers,
    get_stock_check_with_items,
    list_recent_stock_checks,
    list_stock_checks_by_order,
    get_material_history,
    list_orders_using_material,
    list_co_checker_candidates,
    _user_can_edit,
    _resolve_user_names,
    StockCheckPermissionError,
)

router = APIRouter()


async def _to_check_out(db: AsyncSession, head: StockCheck, current_user: dict) -> StockCheckOut:
    """构造 StockCheckOut，附带共同盘点人姓名 + can_edit。"""
    out = StockCheckOut.model_validate(head)
    ids = list(head.co_checker_user_ids or [])
    name_map = await _resolve_user_names(db, ids + ([head.created_by_user_id] if head.created_by_user_id else []))
    out.co_checkers = [{"user_id": int(i), "name": name_map.get(int(i), f"user#{i}")} for i in ids]
    out.can_edit = _user_can_edit(head, current_user)
    return out


@router.post("/stock-check/from-order/{order_no}", response_model=ResponseModel[StockCheckOut])
async def create_from_order(
    order_no: str,
    body: Optional[StockCheckCreate] = None,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    body = body or StockCheckCreate(order_no=order_no)
    try:
        head = await create_stock_check_from_order(
            db,
            order_no=order_no,
            current_user=current_user,
            title=body.title,
            check_date=body.check_date,
            remark=body.remark,
            selected_products=(
                [s.model_dump() for s in body.selected_products]
                if body.selected_products else None
            ),
            co_checker_user_ids=body.co_checker_user_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    head = await get_stock_check_with_items(db, head.id)
    return ResponseModel(data=await _to_check_out(db, head, current_user))


@router.post("/stock-check/from-materials", response_model=ResponseModel[StockCheckOut])
async def create_from_materials(
    body: StockCheckFromMaterialsCreate,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    if not body.material_ids or len(body.material_ids) > 500:
        raise HTTPException(status_code=400, detail="请选择 1~500 个物料")
    try:
        head = await create_stock_check_from_materials(
            db,
            material_ids=body.material_ids,
            current_user=current_user,
            title=body.title,
            check_date=body.check_date,
            remark=body.remark,
            co_checker_user_ids=body.co_checker_user_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    head = await get_stock_check_with_items(db, head.id)
    return ResponseModel(data=await _to_check_out(db, head, current_user))


@router.get("/stock-check/material-candidates", response_model=ResponseModel[PageResult[MaterialCandidateOut]])
async def list_material_candidates_view(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索物料编码/名称/规格"),
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    total, items = await list_material_candidates(
        db, page=page, page_size=page_size, keyword=keyword
    )
    return ResponseModel(data=PageResult(
        total=total,
        page=page,
        page_size=page_size,
        items=[MaterialCandidateOut(**it) for it in items],
    ))


@router.get("/stock-check/material-history", response_model=ResponseModel[list[MaterialHistoryItem]])
async def get_material_history_view(
    material_id: int = Query(..., description="物料ID"),
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_material_history(db, material_id=material_id)
    return ResponseModel(data=[MaterialHistoryItem(**r) for r in rows])


@router.get("/stock-check/material-orders", response_model=ResponseModel[PageResult[MaterialOrderUsageOut]])
async def list_material_orders(
    material_id: int = Query(..., description="物料ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="模糊搜索订单号/客户"),
    sort_by: Optional[str] = Query("req_qty", description="排序字段:req_qty/promised_date/order_qty"),
    sort_order: Optional[str] = Query("desc", description="asc/desc"),
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    total, items = await list_orders_using_material(
        db,
        material_id=material_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return ResponseModel(data=PageResult(
        total=total,
        page=page,
        page_size=page_size,
        items=[MaterialOrderUsageOut(**it) for it in items],
    ))


@router.get("/stock-check/recent", response_model=ResponseModel[PageResult[StockCheckListOut]])
async def recent(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索盘点单号/订单号/标题"),
    status: Optional[str] = Query(None, description="状态筛选,逗号分隔(open/in_progress/completed/cancelled)"),
    check_type: Optional[str] = Query(None, description="盘点类型:order/manual"),
    date_from: Optional[date] = Query(None, description="盘点日期起点 (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="盘点日期终点 (YYYY-MM-DD)"),
    sort_by: Optional[str] = Query(None, description="排序字段:check_no/order_no/check_date/total_materials/checked_materials/total_diff_qty/created_at"),
    sort_order: Optional[str] = Query(None, description="asc/desc,默认 desc"),
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    statuses = [s.strip() for s in (status or "").split(",") if s.strip()] or None
    rows = await list_recent_stock_checks(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=statuses,
        check_type=check_type,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    filter_query = select(StockCheck)
    if keyword:
        like = f"%{keyword}%"
        filter_query = filter_query.where(or_(
            StockCheck.check_no.ilike(like),
            StockCheck.order_no.ilike(like),
            StockCheck.title.ilike(like),
        ))
    if statuses:
        filter_query = filter_query.where(StockCheck.status.in_(statuses))
    if check_type:
        filter_query = filter_query.where(StockCheck.check_type == check_type)
    if date_from:
        filter_query = filter_query.where(StockCheck.check_date >= date_from)
    if date_to:
        filter_query = filter_query.where(StockCheck.check_date <= date_to)
    total = (await db.execute(
        select(func.count()).select_from(filter_query.subquery())
    )).scalar() or 0
    return ResponseModel(data=PageResult(
        total=int(total),
        page=page,
        page_size=page_size,
        items=[StockCheckListOut.model_validate(r) for r in rows],
    ))


@router.get("/stock-check/by-order/{order_no}", response_model=ResponseModel[List[StockCheckListOut]])
async def list_by_order(
    order_no: str,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_stock_checks_by_order(db, order_no)
    return ResponseModel(data=[StockCheckListOut.model_validate(r) for r in rows])


@router.get("/stock-check/{check_id}", response_model=ResponseModel[StockCheckOut])
async def get_detail(
    check_id: int,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    head = await get_stock_check_with_items(db, check_id)
    if not head:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    return ResponseModel(data=await _to_check_out(db, head, current_user))


@router.get("/stock-check/{check_id}/items", response_model=ResponseModel[PageResult[StockCheckItemOut]])
async def list_items(
    check_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    base = select(StockCheckItem).where(StockCheckItem.check_id == check_id).order_by(StockCheckItem.id)
    total = (await db.execute(
        select(func.count(StockCheckItem.id)).where(StockCheckItem.check_id == check_id)
    )).scalar_one()
    rows = (await db.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return ResponseModel(data=PageResult(
        total=int(total or 0),
        page=page,
        page_size=page_size,
        items=[StockCheckItemOut.model_validate(r) for r in rows],
    ))


@router.put("/stock-check/items/{item_id}", response_model=ResponseModel[StockCheckItemOut])
async def update_item(
    item_id: int,
    body: StockCheckItemUpdate,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await update_stock_check_item(
            db,
            item_id,
            actual_qty=body.actual_qty,
            is_checked=body.is_checked,
            remark=body.remark,
            current_user=current_user,
        )
    except StockCheckPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    item = (await db.execute(select(StockCheckItem).where(StockCheckItem.id == item_id))).scalar_one()
    return ResponseModel(data=StockCheckItemOut.model_validate(item))


@router.post("/stock-check/items/batch", response_model=ResponseModel[dict])
async def batch_update(
    body: StockCheckItemBatchUpdate,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        n = await batch_update_items(db, body.check_id, [it.model_dump() for it in body.items], current_user)
    except StockCheckPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResponseModel(data={"updated": n})


@router.post("/stock-check/{check_id}/complete", response_model=ResponseModel[StockCheckOut])
async def complete(
    check_id: int,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await complete_stock_check(db, check_id, current_user)
    except StockCheckPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    head = await get_stock_check_with_items(db, check_id)
    return ResponseModel(data=await _to_check_out(db, head, current_user))


@router.post("/stock-check/{check_id}/cancel", response_model=ResponseModel[StockCheckOut])
async def cancel(
    check_id: int,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await cancel_stock_check(db, check_id, current_user)
    except StockCheckPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    head = await get_stock_check_with_items(db, check_id)
    return ResponseModel(data=await _to_check_out(db, head, current_user))


@router.put("/stock-check/{check_id}/co-checkers", response_model=ResponseModel[StockCheckOut])
async def update_co_checkers(
    check_id: int,
    body: CoCheckersUpdate,
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await set_co_checkers(db, check_id, body.co_checker_user_ids, current_user)
    except StockCheckPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    head = await get_stock_check_with_items(db, check_id)
    return ResponseModel(data=await _to_check_out(db, head, current_user))


@router.get("/stock-check/co-checker-candidates", response_model=ResponseModel[list])
async def co_checker_candidates(
    current_user: dict = Depends(PermissionChecker("materials.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    return ResponseModel(data=await list_co_checker_candidates(db))
