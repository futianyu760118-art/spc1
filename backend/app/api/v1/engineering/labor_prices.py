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
    parse_capacity_metadata,
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
    price: float = Field(ge=0)
    pph: Optional[float] = None
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


class LaborPriceDetailOut(BaseModel):
    id: int
    process_type: str
    gx: Optional[int] = None
    price: float
    pph: Optional[float] = None
    remark: Optional[str] = None


class LaborPriceChangeOut(BaseModel):
    id: int
    bom_code: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
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
    if not payload.details:
        raise HTTPException(status_code=400, detail="至少需要一条工序明细")
    for detail in payload.details:
        if not detail.process_type.strip():
            raise HTTPException(status_code=400, detail="工序不能为空")

    process_names = [detail.process_type.strip() for detail in payload.details]
    normalized_names = [name.casefold() for name in process_names]
    if len(set(normalized_names)) != len(normalized_names):
        raise HTTPException(status_code=400, detail="同一张工价单内工序不能重复")

    status = str(payload.status or "pending").strip().lower()
    if status not in {"draft", "pending"}:
        raise HTTPException(status_code=400, detail="状态只能是草稿或待审批")

    if status == "pending":
        duplicate_rows = (
            await db.execute(
                select(LaborPriceDetail.process_type)
                .join(LaborPriceMain, LaborPriceDetail.main_id == LaborPriceMain.id)
                .where(
                    LaborPriceMain.bom_code == bom_code,
                    LaborPriceMain.status == "pending",
                    LaborPriceDetail.process_type.in_(process_names),
                )
            )
        ).scalars().all()
        if duplicate_rows:
            raise HTTPException(
                status_code=400,
                detail=f"该 BOM 已有待审批工序：{'、'.join(sorted(set(duplicate_rows)))}",
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
        db.add(
            LaborPriceDetail(
                main_id=main.id,
                gx=detail.gx,
                process_type=detail.process_type.strip(),
                price=detail.price,
                pph=detail.pph,
                remark=detail.remark,
            )
        )
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
    current_user: dict = Depends(PermissionChecker("production.labor_price_audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
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

    items = [
        LaborPriceChangeOut(
            id=row.id,
            bom_code=row.bom_code,
            product_code=row.product_code,
            product_name=row.product_name,
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
                    price=float(detail.price or 0),
                    pph=float(detail.pph) if detail.pph is not None else None,
                    remark=detail.remark,
                )
                for detail in row.details
            ],
        )
        for row in rows
    ]
    return ResponseModel(
        data=PageResult(total=total, page=page, page_size=page_size, items=items)
    )

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
    workshop_id: Optional[str] = None
    workshop_name: Optional[str] = None
    oa_main_id: Optional[str] = None


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

    latest: dict[str, CurrentPriceOut] = {}
    for row in rows:
        metadata = parse_capacity_metadata(row.remark)
        process_type = str(row.process_type or "").strip()
        if not process_type:
            continue
        try:
            main_id = int(str(metadata.get("oa_main_id") or "0"))
        except (TypeError, ValueError):
            main_id = 0
        existing = latest.get(process_type)
        existing_main = 0
        if existing:
            try:
                existing_main = int(str(existing.oa_main_id or "0"))
            except (TypeError, ValueError):
                existing_main = 0
        if existing and main_id < existing_main:
            continue
        latest[process_type] = CurrentPriceOut(
            process_type=process_type,
            price=float(metadata.get("gjje") or 0),
            pph=metadata.get("oa_raw_upph"),
            upph=float(row.upph) if row.upph is not None else None,
            workshop_id=metadata.get("oa_workshop_id"),
            workshop_name=metadata.get("oa_workshop_name"),
            oa_main_id=metadata.get("oa_main_id"),
        )
    return ResponseModel(data=sorted(latest.values(), key=lambda item: item.process_type))
