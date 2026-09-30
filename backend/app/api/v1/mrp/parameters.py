"""MRP 参数：方案 / 物料参数。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.basicdata.material import Material
from app.models.mrp.parameter import MrpParameter
from app.models.mrp.scheme import MrpScheme
from app.schemas.common import PageResult, ResponseModel
from app.schemas.mrp.schemas import (
    ParameterOut,
    ParameterUpsertRequest,
    SchemeOut,
    SchemeUpdateRequest,
)
from app.services.mrp.parameter_service import ensure_default_scheme

parameters_router = APIRouter()


@parameters_router.get("/schemes", response_model=ResponseModel[list[SchemeOut]])
async def list_schemes(
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_default_scheme(db)
    rows = (await db.execute(select(MrpScheme).order_by(MrpScheme.id))).scalars().all()
    return ResponseModel(data=[SchemeOut.model_validate(r) for r in rows])


@parameters_router.put("/schemes/{scheme_id}", response_model=ResponseModel[SchemeOut])
async def update_scheme(
    scheme_id: int,
    payload: SchemeUpdateRequest,
    current_user: dict = Depends(PermissionChecker("materials.mrp", "param")),
    db: AsyncSession = Depends(get_db),
):
    scheme = (await db.execute(select(MrpScheme).where(MrpScheme.id == scheme_id))).scalar_one_or_none()
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(scheme, field, value)
    return ResponseModel(data=SchemeOut.model_validate(scheme))


@parameters_router.get("/parameters", response_model=ResponseModel[PageResult[ParameterOut]])
async def list_parameters(
    keyword: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(MrpParameter, Material.material_code, Material.material_name)
        .outerjoin(Material, Material.erp_material_id == MrpParameter.material_id)
    )
    count_query = select(func.count()).select_from(MrpParameter)
    if keyword:
        like = f"%{keyword}%"
        material_ids = (
            await db.execute(
                select(Material.erp_material_id).where(
                    Material.material_code.ilike(like) | Material.material_name.ilike(like)
                )
            )
        ).scalars().all()
        query = query.where(MrpParameter.material_id.in_(list(material_ids) or [0]))
        count_query = count_query.where(MrpParameter.material_id.in_(list(material_ids) or [0]))
    total = (await db.execute(count_query)).scalar() or 0
    rows = (
        await db.execute(query.order_by(MrpParameter.material_id).offset((page - 1) * page_size).limit(page_size))
    ).all()
    items = []
    for row in rows:
        item = ParameterOut.model_validate(row[0])
        item.material_code = row[1]
        item.material_name = row[2]
        items.append(item)
    return ResponseModel(
        data=PageResult(
            total=int(total), page=page, page_size=page_size,
            items=items,
        )
    )


async def _resolve_material_id(db: AsyncSession, payload: ParameterUpsertRequest) -> int:
    if payload.material_id is not None:
        exists = (
            await db.execute(
                select(Material.erp_material_id).where(Material.erp_material_id == payload.material_id)
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"物料不存在：{payload.material_id}")
        return payload.material_id
    code = (payload.material_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="请提供 material_id 或 material_code")
    resolved = (
        await db.execute(select(Material.erp_material_id).where(Material.material_code == code))
    ).scalar_one_or_none()
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"物料编码不存在：{code}")
    return int(resolved)


async def _upsert_parameter(db: AsyncSession, payload: ParameterUpsertRequest) -> MrpParameter:
    material_id = await _resolve_material_id(db, payload)
    row = (
        await db.execute(
            select(MrpParameter).where(MrpParameter.material_id == material_id)
        )
    ).scalar_one_or_none()
    values = payload.model_dump()
    values.pop("material_code", None)
    values["material_id"] = material_id
    if row is None:
        row = MrpParameter(**values, data_source="manual")
        db.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
        row.data_source = "manual"
    await db.flush()
    return row


@parameters_router.put("/parameters", response_model=ResponseModel[ParameterOut])
async def upsert_parameter(
    payload: ParameterUpsertRequest,
    current_user: dict = Depends(PermissionChecker("materials.mrp", "param")),
    db: AsyncSession = Depends(get_db),
):
    row = await _upsert_parameter(db, payload)
    return ResponseModel(data=ParameterOut.model_validate(row))


@parameters_router.post("/parameters/import", response_model=ResponseModel[dict])
async def import_parameters(
    rows: list[ParameterUpsertRequest],
    current_user: dict = Depends(PermissionChecker("materials.mrp", "param")),
    db: AsyncSession = Depends(get_db),
):
    saved = 0
    for payload in rows:
        await _upsert_parameter(db, payload)
        saved += 1
    return ResponseModel(data={"saved": saved})
