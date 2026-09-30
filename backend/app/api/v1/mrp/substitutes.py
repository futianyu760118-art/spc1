"""MRP 替代规则：列表 / 新增更新。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.basicdata.material import Material
from app.models.mrp.substitute import MrpSubstitute
from app.schemas.common import PageResult, ResponseModel
from app.schemas.mrp.schemas import SubstituteOut, SubstituteUpsertRequest

substitutes_router = APIRouter()


async def _resolve_material_id(
    db: AsyncSession,
    material_id: Optional[int],
    material_code: Optional[str],
) -> int:
    if material_id is not None:
        exists = (
            await db.execute(
                select(Material.erp_material_id).where(Material.erp_material_id == material_id)
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"物料不存在：{material_id}")
        return int(material_id)
    code = (material_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="请提供物料 ID 或物料编码")
    resolved = (
        await db.execute(select(Material.erp_material_id).where(Material.material_code == code))
    ).scalar_one_or_none()
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"物料编码不存在：{code}")
    return int(resolved)


async def _load_material_info(db: AsyncSession, material_ids: list[int]) -> dict[int, tuple]:
    rows = (
        await db.execute(
            select(Material.erp_material_id, Material.material_code, Material.material_name).where(
                Material.erp_material_id.in_(material_ids)
            )
        )
    ).all()
    return {int(row[0]): (row[1], row[2]) for row in rows}


def _fill_material_info(
    item: SubstituteOut,
    main_info: Optional[tuple],
    substitute_info: Optional[tuple],
) -> SubstituteOut:
    main_code, main_name = main_info if main_info else (None, None)
    sub_code, sub_name = substitute_info if substitute_info else (None, None)
    item.main_material_code = main_code or ""
    item.main_material_name = main_name or ""
    item.substitute_material_code = sub_code or ""
    item.substitute_material_name = sub_name or ""
    return item


@substitutes_router.get("/substitutes", response_model=ResponseModel[PageResult[SubstituteOut]])
async def list_substitutes(
    keyword: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(PermissionChecker("materials.mrp", "read")),
    db: AsyncSession = Depends(get_db),
):
    main_material = aliased(Material)
    substitute_material = aliased(Material)
    main_join = main_material.erp_material_id == MrpSubstitute.main_material_id
    substitute_join = substitute_material.erp_material_id == MrpSubstitute.substitute_material_id
    query = (
        select(
            MrpSubstitute,
            main_material.material_code,
            main_material.material_name,
            substitute_material.material_code,
            substitute_material.material_name,
        )
        .outerjoin(main_material, main_join)
        .outerjoin(substitute_material, substitute_join)
    )
    count_query = (
        select(func.count())
        .select_from(MrpSubstitute)
        .outerjoin(main_material, main_join)
        .outerjoin(substitute_material, substitute_join)
    )
    if keyword:
        like = f"%{keyword}%"
        condition = (
            main_material.material_code.ilike(like)
            | main_material.material_name.ilike(like)
            | substitute_material.material_code.ilike(like)
            | substitute_material.material_name.ilike(like)
        )
        query = query.where(condition)
        count_query = count_query.where(condition)
    total = (await db.execute(count_query)).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(MrpSubstitute.main_material_id, MrpSubstitute.priority, MrpSubstitute.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = []
    for row in rows:
        item = SubstituteOut.model_validate(row[0])
        _fill_material_info(item, (row[1], row[2]), (row[3], row[4]))
        items.append(item)
    return ResponseModel(
        data=PageResult(
            total=int(total), page=page, page_size=page_size,
            items=items,
        )
    )


@substitutes_router.put("/substitutes", response_model=ResponseModel[SubstituteOut])
async def upsert_substitute(
    payload: SubstituteUpsertRequest,
    current_user: dict = Depends(PermissionChecker("materials.mrp", "param")),
    db: AsyncSession = Depends(get_db),
):
    main_material_id = await _resolve_material_id(
        db, payload.main_material_id, payload.main_material_code
    )
    substitute_material_id = await _resolve_material_id(
        db, payload.substitute_material_id, payload.substitute_material_code
    )
    if main_material_id == substitute_material_id:
        raise HTTPException(status_code=400, detail="主料与替代料不能相同")
    if payload.policy == "ratio" and payload.ratio is None:
        raise HTTPException(status_code=400, detail="policy=ratio 时请提供比例 ratio")
    if payload.valid_from and payload.valid_to and payload.valid_from > payload.valid_to:
        raise HTTPException(status_code=400, detail="生效日期不能晚于失效日期")
    row = (
        await db.execute(
            select(MrpSubstitute).where(
                MrpSubstitute.main_material_id == main_material_id,
                MrpSubstitute.substitute_material_id == substitute_material_id,
            )
        )
    ).scalar_one_or_none()
    values = payload.model_dump()
    values.pop("main_material_code", None)
    values.pop("substitute_material_code", None)
    values["main_material_id"] = main_material_id
    values["substitute_material_id"] = substitute_material_id
    if row is None:
        row = MrpSubstitute(**values, data_source="manual")
        db.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
        row.data_source = "manual"
    await db.flush()
    info = await _load_material_info(db, [main_material_id, substitute_material_id])
    out = SubstituteOut.model_validate(row)
    _fill_material_info(out, info.get(main_material_id), info.get(substitute_material_id))
    return ResponseModel(data=out)
