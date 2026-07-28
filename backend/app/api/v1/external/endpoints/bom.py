"""BOM 对外接口

为外部系统提供 BOM 列表查询，支持按物料代码筛选。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.basicdata.bom import Bom
from app.models.basicdata.material import Material

from ..registry import register_external, ExternalCallContext


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@register_external(
    "boms.list",
    "BOM列表",
    method="GET",
    path="/boms/list",
    description="BOM列表查询，支持按物料代码、BOM编号、版本号、类型、使用状态、增量同步",
    tags=["主数据"],
)
async def boms_list(ctx: ExternalCallContext) -> dict:
    """BOM列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        material_code: 物料代码精确匹配（关联 scm_material 表）
        bom_no: BOM编号模糊匹配
        bom_version: BOM版本号精确匹配
        bom_type: BOM类型精确匹配
        use_status: 使用状态精确匹配
        updated_after: 增量同步 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    material_code = params.get("material_code")
    bom_no = params.get("bom_no")
    bom_version = params.get("bom_version")
    bom_type = params.get("bom_type")
    use_status = params.get("use_status")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(Bom)
    need_join_material = False

    if material_code:
        need_join_material = True

    if need_join_material:
        query = query.join(Material, Bom.material_id == Material.material_id)

    count_query = select(func.count()).select_from(query.subquery())

    if material_code:
        query = query.where(Material.material_code == material_code)
        count_query = select(func.count()).select_from(query.subquery())

    if bom_no:
        query = query.where(Bom.bom_no.ilike(f"%{bom_no}%"))
        count_query = select(func.count()).select_from(query.subquery())

    if bom_version:
        query = query.where(Bom.bom_version == bom_version)
        count_query = select(func.count()).select_from(query.subquery())

    if bom_type:
        query = query.where(Bom.bom_type == bom_type)
        count_query = select(func.count()).select_from(query.subquery())

    if use_status:
        query = query.where(Bom.use_status == use_status)
        count_query = select(func.count()).select_from(query.subquery())

    if updated_after:
        query = query.where(Bom.update_time >= updated_after)
        count_query = select(func.count()).select_from(query.subquery())

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Bom.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    if need_join_material:
        rows = (await db.execute(query)).all()
        items = [{
            "bom_id": row.Bom.bom_id,
            "bom_no": row.Bom.bom_no,
            "material_id": row.Bom.material_id,
            "material_code": row.Material.material_code,
            "material_name": row.Material.material_name,
            "parent_material_id": row.Bom.parent_material_id,
            "bom_version": row.Bom.bom_version,
            "bom_type": row.Bom.bom_type,
            "base_qty": float(row.Bom.base_qty) if row.Bom.base_qty is not None else None,
            "unit_id": row.Bom.unit_id,
            "use_status": row.Bom.use_status,
            "disabled_status": row.Bom.disabled_status,
            "void_flag": row.Bom.void_flag,
            "update_time": row.Bom.update_time.isoformat() if row.Bom.update_time else None,
        } for row in rows]
    else:
        rows = (await db.execute(query)).scalars().all()
        items = [{
            "bom_id": r.bom_id,
            "bom_no": r.bom_no,
            "material_id": r.material_id,
            "material_code": None,
            "material_name": None,
            "parent_material_id": r.parent_material_id,
            "bom_version": r.bom_version,
            "bom_type": r.bom_type,
            "base_qty": float(r.base_qty) if r.base_qty is not None else None,
            "unit_id": r.unit_id,
            "use_status": r.use_status,
            "disabled_status": r.disabled_status,
            "void_flag": r.void_flag,
            "update_time": r.update_time.isoformat() if r.update_time else None,
        } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
