import asyncio
import time
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.production.labor_price import LaborPriceDetail, LaborPriceMain
from app.models.production.product_process_capacity import (
    ProductProcessCapacity,
    build_capacity_metadata_remark,
    parse_capacity_metadata,
    resolve_capacity_upph,
)
from app.services.production.product_process_capacity_sync_service import (
    ProductProcessCapacitySyncService,
)
from app.schemas.common import PageResult, ResponseModel

router = APIRouter()


class LaborPriceOut(BaseModel):
    id: int
    bom_code: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    process_type: Optional[str] = None
    workshop_name: Optional[str] = None
    price: Optional[float] = None
    oa_pph: Optional[float] = None
    upph: Optional[float] = None
    bottleneck_hours: Optional[float] = None
    standard_capacity: Optional[float] = None
    manpower: Optional[float] = None
    remark: Optional[str] = None
    oa_main_id: Optional[str] = None
    source: Optional[str] = None
    last_sync_time: Optional[datetime] = None


@router.get("/labor-prices", response_model=ResponseModel[PageResult[LaborPriceOut]])
async def list_labor_prices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    process_type: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    """工价查询（当前读取本地已同步的 OA 工价数据，只读）。"""
    conditions = [ProductProcessCapacity.is_active == True]
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                ProductProcessCapacity.bom_code.ilike(like),
                ProductProcessCapacity.product_code.ilike(like),
                ProductProcessCapacity.product_name.ilike(like),
                ProductProcessCapacity.process_type.ilike(like),
            )
        )
    if process_type:
        conditions.append(ProductProcessCapacity.process_type == process_type)

    total = (
        await db.execute(
            select(func.count(ProductProcessCapacity.id)).where(*conditions)
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            select(ProductProcessCapacity)
            .where(*conditions)
            .order_by(
                ProductProcessCapacity.bom_code.asc().nulls_last(),
                ProductProcessCapacity.process_type.asc(),
                ProductProcessCapacity.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = []
    for row in rows:
        metadata = parse_capacity_metadata(row.remark)
        items.append(
            LaborPriceOut(
                id=row.id,
                bom_code=row.bom_code,
                product_code=row.product_code,
                product_name=row.product_name,
                process_type=row.process_type,
                workshop_name=metadata.get("oa_workshop_name"),
                price=metadata.get("gjje"),
                oa_pph=metadata.get("oa_raw_upph"),
                upph=float(row.upph) if row.upph is not None else None,
                bottleneck_hours=metadata.get("bottleneck_hours"),
                standard_capacity=metadata.get("standard_capacity"),
                manpower=metadata.get("oa_manpower"),
                remark=metadata.get("raw_remark"),
                oa_main_id=metadata.get("oa_main_id"),
                source=row.source,
                last_sync_time=row.last_sync_time,
            )
        )

    return ResponseModel(
        data=PageResult(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )
    )

class LaborPriceDetailIn(BaseModel):
    process_type: str = Field(min_length=1)
    gx: Optional[int] = None
    original_price: Optional[float] = Field(None, ge=0)
    price: float = Field(ge=0)
    pph: Optional[float] = None
    bottleneck_hours: Optional[float] = None
    standard_capacity: Optional[float] = None
    manpower: Optional[int] = None
    oa_detail_id: Optional[str] = None
    remark: Optional[str] = None


class LaborPriceChangeCreate(BaseModel):
    bom_code: str = Field(min_length=1)
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    workshop_id: Optional[str] = None
    workshop_name: Optional[str] = None
    effective_date: Optional[date] = None
    reason: Optional[str] = None
    remark: Optional[str] = None
    status: Optional[str] = "pending"
    details: list[LaborPriceDetailIn] = Field(min_length=1)


class LaborPriceChangeUpdate(BaseModel):
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    workshop_id: Optional[str] = None
    workshop_name: Optional[str] = None
    effective_date: Optional[date] = None
    reason: Optional[str] = None
    remark: Optional[str] = None
    status: Optional[str] = None
    details: list[LaborPriceDetailIn] = Field(min_length=1)


class LaborPriceDetailOut(BaseModel):
    id: int
    process_type: str
    gx: Optional[int] = None
    original_price: Optional[float] = None
    price: float
    pph: Optional[float] = None
    bottleneck_hours: Optional[float] = None
    standard_capacity: Optional[float] = None
    manpower: Optional[int] = None
    oa_detail_id: Optional[str] = None
    remark: Optional[str] = None


class LaborPriceChangeOut(BaseModel):
    id: int
    bom_code: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    workshop_id: Optional[str] = None
    workshop_name: Optional[str] = None
    status: str
    source: str
    effective_date: Optional[date] = None
    reason: Optional[str] = None
    remark: Optional[str] = None
    applicant: Optional[str] = None
    approver: Optional[str] = None
    created_at: Optional[datetime] = None
    details: list[LaborPriceDetailOut] = Field(default_factory=list)


def _serialize_labor_price_change(row: LaborPriceMain) -> LaborPriceChangeOut:
    return LaborPriceChangeOut(
        id=row.id,
        bom_code=row.bom_code,
        product_code=row.product_code,
        product_name=row.product_name,
        workshop_id=row.workshop_id,
        workshop_name=row.workshop_name,
        status=row.status,
        source=row.source,
        effective_date=row.effective_date,
        reason=row.reason,
        remark=row.remark,
        applicant=row.applicant,
        approver=row.approver,
        created_at=row.created_at,
        details=[
            LaborPriceDetailOut(
                id=detail.id,
                process_type=detail.process_type,
                gx=detail.gx,
                original_price=float(detail.original_price) if detail.original_price is not None else None,
                price=float(detail.price or 0),
                pph=float(detail.pph) if detail.pph is not None else None,
                bottleneck_hours=float(detail.bottleneck_hours) if detail.bottleneck_hours is not None else None,
                standard_capacity=float(detail.standard_capacity) if detail.standard_capacity is not None else None,
                manpower=detail.manpower,
                oa_detail_id=detail.oa_detail_id,
                remark=detail.remark,
            )
            for detail in row.details
        ],
    )


def _detail_key(detail: LaborPriceDetailIn) -> tuple[str, str, str]:
    return (
        detail.process_type.strip().casefold(),
        (detail.remark or "").strip().casefold(),
        (detail.oa_detail_id or "").strip(),
    )


def _validate_details(details: list[LaborPriceDetailIn]) -> None:
    if not details:
        raise HTTPException(status_code=400, detail="至少需要一条工序明细")
    for detail in details:
        if not detail.process_type.strip():
            raise HTTPException(status_code=400, detail="工序不能为空")
    keys = [_detail_key(detail) for detail in details]
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=400, detail="同一工序和备注不能重复")


async def _ensure_no_pending_conflict(
    db: AsyncSession,
    *,
    bom_code: str,
    details: list[LaborPriceDetailIn],
    exclude_main_id: int | None = None,
) -> None:
    process_names = [detail.process_type.strip() for detail in details]
    query = (
        select(
            LaborPriceDetail.process_type,
            LaborPriceDetail.remark,
            LaborPriceDetail.oa_detail_id,
        )
        .join(LaborPriceMain, LaborPriceDetail.main_id == LaborPriceMain.id)
        .where(
            LaborPriceMain.bom_code == bom_code,
            LaborPriceMain.status == "pending",
            LaborPriceDetail.process_type.in_(process_names),
        )
    )
    if exclude_main_id is not None:
        query = query.where(LaborPriceMain.id != exclude_main_id)
    pending_rows = (await db.execute(query)).all()
    pending_keys = {
        (
            str(process or "").strip().casefold(),
            str(remark or "").strip().casefold(),
            str(oa_detail_id or "").strip(),
        )
        for process, remark, oa_detail_id in pending_rows
    }
    detail_by_key = {_detail_key(detail): detail for detail in details}
    conflicts = [key for key in detail_by_key if key in pending_keys]
    if conflicts:
        labels = []
        for key in conflicts:
            detail = detail_by_key[key]
            labels.append(
                detail.process_type.strip()
                + (f" / {detail.remark.strip()}" if detail.remark else "")
            )
        raise HTTPException(
            status_code=400,
            detail=f"该 BOM 已有待审批明细：{'、'.join(sorted(labels))}",
        )


def _build_labor_price_detail(
    main_id: int,
    detail: LaborPriceDetailIn,
) -> LaborPriceDetail:
    return LaborPriceDetail(
        main_id=main_id,
        gx=detail.gx,
        process_type=detail.process_type.strip(),
        original_price=detail.original_price,
        price=detail.price,
        pph=detail.pph,
        bottleneck_hours=detail.bottleneck_hours,
        standard_capacity=detail.standard_capacity,
        manpower=detail.manpower,
        oa_detail_id=detail.oa_detail_id,
        remark=detail.remark,
    )


@router.post("/labor-prices/changes", response_model=ResponseModel[dict])
async def create_labor_price_change(
    payload: LaborPriceChangeCreate,
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "create")),
    db: AsyncSession = Depends(get_db),
):
    """新建工价变更单（先保存为待审批，不立即影响排产）。"""
    bom_code = payload.bom_code.strip()
    if not bom_code:
        raise HTTPException(status_code=400, detail="BOM 不能为空")
    _validate_details(payload.details)

    status = str(payload.status or "pending").strip().lower()
    if status not in {"draft", "pending"}:
        raise HTTPException(status_code=400, detail="状态只能是草稿或待审批")

    if status == "pending":
        await _ensure_no_pending_conflict(
            db, bom_code=bom_code, details=payload.details
        )

    main = LaborPriceMain(
        bom_code=bom_code,
        product_code=(payload.product_code or "").strip() or None,
        product_name=(payload.product_name or "").strip() or None,
        workshop_id=(payload.workshop_id or "").strip() or None,
        workshop_name=(payload.workshop_name or "").strip() or None,
        status=status,
        source="manual",
        effective_date=payload.effective_date,
        version=1,
        reason=payload.reason,
        remark=payload.remark,
        applicant=current_user["username"],
    )
    db.add(main)
    await db.flush()
    for detail in payload.details:
        db.add(_build_labor_price_detail(main.id, detail))
    await db.flush()
    return ResponseModel(data={"id": main.id, "status": main.status})


@router.get(
    "/labor-prices/changes",
    response_model=ResponseModel[PageResult[LaborPriceChangeOut]],
)
async def list_labor_price_changes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    bom_code: Optional[str] = Query(None),
    process_type: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if bom_code:
        conditions.append(LaborPriceMain.bom_code == bom_code.strip())
    if process_type:
        conditions.append(
            LaborPriceMain.id.in_(
                select(LaborPriceDetail.main_id).where(
                    LaborPriceDetail.process_type == process_type.strip()
                )
            )
        )
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                LaborPriceMain.bom_code.ilike(like),
                LaborPriceMain.product_code.ilike(like),
                LaborPriceMain.product_name.ilike(like),
                LaborPriceMain.applicant.ilike(like),
            )
        )
    if status:
        conditions.append(LaborPriceMain.status == status)

    total = (
        await db.execute(select(func.count(LaborPriceMain.id)).where(*conditions))
    ).scalar() or 0
    rows = (
        await db.execute(
            select(LaborPriceMain)
            .where(*conditions)
            .options(selectinload(LaborPriceMain.details))
            .order_by(LaborPriceMain.created_at.desc(), LaborPriceMain.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = [_serialize_labor_price_change(row) for row in rows]
    return ResponseModel(
        data=PageResult(total=total, page=page, page_size=page_size, items=items)
    )


@router.get(
    "/labor-prices/changes/{change_id}",
    response_model=ResponseModel[LaborPriceChangeOut],
)
async def get_labor_price_change(
    change_id: int,
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(LaborPriceMain)
            .where(LaborPriceMain.id == change_id)
            .options(selectinload(LaborPriceMain.details))
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="工价变更单不存在")
    return ResponseModel(data=_serialize_labor_price_change(row))


@router.put(
    "/labor-prices/changes/{change_id}",
    response_model=ResponseModel[LaborPriceChangeOut],
)
async def update_labor_price_change(
    change_id: int,
    payload: LaborPriceChangeUpdate,
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "update")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(LaborPriceMain)
            .where(LaborPriceMain.id == change_id)
            .options(selectinload(LaborPriceMain.details))
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="工价变更单不存在")
    if row.status != "draft":
        raise HTTPException(status_code=400, detail="只有草稿可以修改")

    _validate_details(payload.details)
    status = str(payload.status or row.status).strip().lower()
    if status not in {"draft", "pending"}:
        raise HTTPException(status_code=400, detail="状态只能是草稿或待审批")
    if status == "pending":
        await _ensure_no_pending_conflict(
            db,
            bom_code=row.bom_code or "",
            details=payload.details,
            exclude_main_id=row.id,
        )

    row.product_code = (payload.product_code or "").strip() or None
    row.product_name = (payload.product_name or "").strip() or None
    row.workshop_id = (payload.workshop_id or "").strip() or None
    row.workshop_name = (payload.workshop_name or "").strip() or None
    row.effective_date = payload.effective_date
    row.reason = payload.reason
    row.remark = payload.remark
    row.status = status

    row.details.clear()
    await db.flush()
    for detail in payload.details:
        db.add(_build_labor_price_detail(row.id, detail))
    await db.flush()

    refreshed = (
        await db.execute(
            select(LaborPriceMain)
            .where(LaborPriceMain.id == row.id)
            .options(selectinload(LaborPriceMain.details))
        )
    ).scalar_one()
    return ResponseModel(data=_serialize_labor_price_change(refreshed))


@router.delete(
    "/labor-prices/changes/{change_id}",
    response_model=ResponseModel[dict],
)
async def delete_labor_price_change(
    change_id: int,
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "delete")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(LaborPriceMain, change_id)
    if not row:
        raise HTTPException(status_code=404, detail="工价变更单不存在")
    if row.status != "draft":
        raise HTTPException(status_code=400, detail="只有草稿可以删除，历史记录永久保留")
    await db.delete(row)
    await db.flush()
    return ResponseModel(data={"id": change_id})


async def _find_capacity_row(
    db: AsyncSession,
    main: LaborPriceMain,
    detail: LaborPriceDetail,
) -> ProductProcessCapacity | None:
    if detail.oa_detail_id:
        row = (
            await db.execute(
                select(ProductProcessCapacity).where(
                    ProductProcessCapacity.oa_detail_id == detail.oa_detail_id
                )
            )
        ).scalars().first()
        if row:
            return row

    rows = (
        await db.execute(
            select(ProductProcessCapacity).where(
                ProductProcessCapacity.bom_code == main.bom_code,
                ProductProcessCapacity.process_type == detail.process_type,
            )
        )
    ).scalars().all()
    target_remark = (detail.remark or "").strip()
    if target_remark:
        for row in rows:
            metadata = parse_capacity_metadata(row.remark)
            if (metadata.get("raw_remark") or "").strip() == target_remark:
                return row
    if len(rows) == 1 and not target_remark:
        return rows[0]
    return None


async def _apply_labor_price_detail(
    db: AsyncSession,
    main: LaborPriceMain,
    detail: LaborPriceDetail,
) -> ProductProcessCapacity:
    row = await _find_capacity_row(db, main, detail)
    metadata = parse_capacity_metadata(row.remark) if row else {}
    effective_price = detail.price
    oa_raw_upph = metadata.get("oa_raw_upph")
    if oa_raw_upph is None:
        oa_raw_upph = detail.pph
    upph_result = resolve_capacity_upph(
        workshop_name=metadata.get("oa_workshop_name"),
        process_type=detail.process_type,
        gjje=effective_price,
        oa_raw_upph=oa_raw_upph,
        manpower=metadata.get("manpower"),
        hour_price=metadata.get("hour_price"),
        manual_upph=metadata.get("manual_upph"),
    )
    remark = build_capacity_metadata_remark(
        oa_main_id=metadata.get("oa_main_id"),
        oa_workshop_id=metadata.get("oa_workshop_id"),
        oa_workshop_name=metadata.get("oa_workshop_name"),
        gjje=effective_price,
        oa_gjje=metadata.get("oa_gjje") or metadata.get("gjje"),
        manual_price=effective_price,
        price_source="manual",
        oa_raw_upph=upph_result.get("oa_raw_upph"),
        formula_upph=upph_result.get("formula_upph"),
        effective_upph=upph_result.get("effective_upph"),
        manual_upph=upph_result.get("manual_upph"),
        upph_source=upph_result.get("upph_source"),
        manpower=upph_result.get("manpower"),
        hour_price=upph_result.get("hour_price"),
        oa_manpower=metadata.get("oa_manpower") or detail.manpower,
        bottleneck_hours=metadata.get("bottleneck_hours") or detail.bottleneck_hours,
        standard_capacity=metadata.get("standard_capacity") or detail.standard_capacity,
        raw_remark=detail.remark or metadata.get("raw_remark"),
    )
    new_upph = upph_result.get("effective_upph") or 0
    if row is None:
        row = ProductProcessCapacity(
            oa_detail_id=detail.oa_detail_id,
            bom_code=main.bom_code,
            product_code=main.product_code or main.bom_code or "",
            product_name=main.product_name,
            process_type=detail.process_type,
            upph=new_upph,
            source="manual",
            is_active=True,
            remark=remark,
        )
        db.add(row)
    else:
        row.upph = new_upph
        row.source = "manual"
        row.is_active = True
        row.remark = remark
    return row


@router.post(
    "/labor-prices/changes/{change_id}/approve",
    response_model=ResponseModel[dict],
)
async def approve_labor_price_change(
    change_id: int,
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "update")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(LaborPriceMain)
            .where(LaborPriceMain.id == change_id)
            .options(selectinload(LaborPriceMain.details))
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="工价变更单不存在")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail="只有待审批单可以审批")

    product_codes = {row.product_code} if row.product_code else set()
    bom_codes = {row.bom_code} if row.bom_code else set()
    for detail in row.details:
        await _apply_labor_price_detail(db, row, detail)

    row.status = "approved"
    row.approver = current_user["username"]
    row.approved_at = datetime.now()
    await db.flush()

    affected_plans = 0
    refreshed_snapshots = 0
    try:
        affected_plans = await ProductProcessCapacitySyncService.mark_affected_schedule_plans(
            db,
            product_codes,
            reason="工价审批通过",
        )
        if bom_codes:
            refreshed_snapshots = await ProductProcessCapacitySyncService(
                db
            )._refresh_affected_order_snapshots(bom_codes)
    except Exception:
        # 排产快照刷新失败不回滚工价审批
        pass

    return ResponseModel(
        data={
            "id": row.id,
            "status": row.status,
            "affected_schedule_plans": affected_plans,
            "refreshed_snapshots": refreshed_snapshots,
        }
    )


@router.post(
    "/labor-prices/changes/{change_id}/reject",
    response_model=ResponseModel[dict],
)
async def reject_labor_price_change(
    change_id: int,
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "update")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(LaborPriceMain, change_id)
    if not row:
        raise HTTPException(status_code=404, detail="工价变更单不存在")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail="只有待审批单可以驳回")
    row.status = "rejected"
    row.approver = current_user["username"]
    row.approved_at = datetime.now()
    await db.flush()
    return ResponseModel(data={"id": row.id, "status": row.status})


class BomOptionOut(BaseModel):
    bom_code: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    workshop_name: Optional[str] = None
    erp_cls_id: Optional[str] = None
    process_count: int = 0


_BOM_OPTIONS_CACHE: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_BOM_OPTIONS_CACHE_TTL_SECONDS = 300


def _fetch_boms_from_k3(keyword: str, limit: int) -> list[dict]:
    settings = get_settings()
    if not settings.ERP_DB_URL:
        raise RuntimeError("ERP_DB_URL 未配置")
    url = settings.ERP_DB_URL
    for param in ["TrustServerCertificate=yes", "Encrypt=no"]:
        if param.split("=")[0] not in url:
            url += f"&{param}" if "?" in url else f"?{param}"
    engine = create_engine(
        url,
        connect_args={"login_timeout": 10, "timeout": 20},
    )
    try:
        keyword = keyword.strip()
        where_sql = ""
        params: dict[str, str] = {}
        if keyword:
            where_sql = (
                "WHERE a.FBOMNumber LIKE :kw "
                "OR c.FNumber LIKE :kw "
                "OR c.FName LIKE :kw"
            )
            params["kw"] = f"%{keyword}%"
        sql = f"""
            SELECT DISTINCT TOP {int(limit)}
                a.FInterID, a.FBOMNumber,
                c.FItemID, c.FNumber, c.FName, c.FErpClsID
            FROM k3sv.AIS20161019115614.dbo.ICBOM a
            LEFT JOIN k3sv.AIS20161019115614.dbo.t_ICItem c
                ON a.FItemID = c.FItemID
            {where_sql}
            ORDER BY a.FBOMNumber
        """
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [
            {
                "bom_code": str(row.get("FBOMNumber") or "").strip(),
                "product_code": str(row.get("FNumber") or "").strip() or None,
                "product_name": str(row.get("FName") or "").strip() or None,
                "erp_cls_id": str(row.get("FErpClsID") or "").strip() or None,
                "workshop_name": None,
                "process_count": 0,
            }
            for row in rows
            if str(row.get("FBOMNumber") or "").strip()
        ]
    finally:
        engine.dispose()


class CurrentPriceOut(BaseModel):
    process_type: str
    price: float
    pph: Optional[float] = None
    upph: Optional[float] = None
    bottleneck_hours: Optional[float] = None
    standard_capacity: Optional[float] = None
    manpower: Optional[float] = None
    workshop_id: Optional[str] = None
    workshop_name: Optional[str] = None
    oa_main_id: Optional[str] = None
    oa_detail_id: Optional[str] = None
    remark: Optional[str] = None


@router.get("/labor-prices/boms", response_model=ResponseModel[list[BomOptionOut]])
async def list_labor_price_boms(
    keyword: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    keyword_value = (keyword or "").strip()
    cache_key = (keyword_value.casefold(), limit)
    cached = _BOM_OPTIONS_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _BOM_OPTIONS_CACHE_TTL_SECONDS:
        return ResponseModel(data=[BomOptionOut(**item) for item in cached[1]])

    try:
        rows = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                _fetch_boms_from_k3,
                keyword_value,
                limit,
            ),
            timeout=25,
        )
        grouped: dict[str, dict] = {}
        for row in rows:
            code = str(row.get("bom_code") or "").strip()
            if code and code not in grouped:
                grouped[code] = row
        result = list(grouped.values())
        _BOM_OPTIONS_CACHE[cache_key] = (time.time(), result)
        return ResponseModel(data=[BomOptionOut(**item) for item in result])
    except Exception:
        # ERP 不可用时退回本地已同步的产能 BOM，保证表单还能用
        pass

    conditions = [ProductProcessCapacity.is_active == True]
    if keyword_value:
        like = f"%{keyword_value}%"
        conditions.append(
            or_(
                ProductProcessCapacity.bom_code.ilike(like),
                ProductProcessCapacity.product_code.ilike(like),
                ProductProcessCapacity.product_name.ilike(like),
            )
        )
    rows = (
        await db.execute(
            select(
                ProductProcessCapacity.bom_code,
                ProductProcessCapacity.product_code,
                ProductProcessCapacity.product_name,
                ProductProcessCapacity.remark,
            )
            .where(*conditions)
            .order_by(ProductProcessCapacity.bom_code.asc().nulls_last())
            .limit(2000)
        )
    ).all()

    grouped: dict[str, BomOptionOut] = {}
    for bom_code, product_code, product_name, remark in rows:
        code = str(bom_code or "").strip()
        if not code or code in grouped:
            continue
        metadata = parse_capacity_metadata(remark)
        grouped[code] = BomOptionOut(
            bom_code=code,
            product_code=product_code,
            product_name=product_name,
            workshop_name=metadata.get("oa_workshop_name"),
            process_count=1,
        )
        if len(grouped) >= limit:
            break
    return ResponseModel(data=list(grouped.values()))


@router.get(
    "/labor-prices/current",
    response_model=ResponseModel[list[CurrentPriceOut]],
)
async def list_current_labor_prices(
    bom_code: str = Query(..., min_length=1),
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(ProductProcessCapacity)
            .where(
                ProductProcessCapacity.is_active == True,
                ProductProcessCapacity.bom_code == bom_code.strip(),
            )
            .order_by(ProductProcessCapacity.process_type.asc())
        )
    ).scalars().all()

    items: list[CurrentPriceOut] = []
    for row in rows:
        metadata = parse_capacity_metadata(row.remark)
        process_type = str(row.process_type or "").strip()
        if not process_type:
            continue
        items.append(
            CurrentPriceOut(
                process_type=process_type,
                price=float(metadata.get("gjje") or 0),
                pph=metadata.get("oa_raw_upph"),
                upph=float(row.upph) if row.upph is not None else None,
                bottleneck_hours=metadata.get("bottleneck_hours"),
                standard_capacity=metadata.get("standard_capacity"),
                manpower=metadata.get("oa_manpower"),
                workshop_id=metadata.get("oa_workshop_id"),
                workshop_name=metadata.get("oa_workshop_name"),
                oa_main_id=metadata.get("oa_main_id"),
                oa_detail_id=row.oa_detail_id,
                remark=metadata.get("raw_remark"),
            )
        )
    return ResponseModel(
        data=sorted(items, key=lambda item: (item.process_type, item.oa_detail_id or ""))
    )
