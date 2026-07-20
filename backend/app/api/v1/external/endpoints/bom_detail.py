"""BOM明细 对外接口

为外部系统提供 BOM明细列表查询，支持按 BOM ID、物料ID 筛选。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func

from app.models.basicdata.bom_detail import BomDetail
from app.models.basicdata.material import Material
from app.models.basicdata.bom import Bom

from ..registry import register_external, ExternalCallContext


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@register_external(
    "bom_details.list",
    "BOM明细列表",
    method="GET",
    path="/bom-details/list",
    description="BOM明细列表查询，支持按BOM ID、物料ID、增量同步",
    tags=["主数据"],
)
async def bom_details_list(ctx: ExternalCallContext) -> dict:
    """BOM明细列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        bom_id: BOM ID精确匹配
        material_id: 物料ID精确匹配（BOM明细中的物料）
        updated_after: 增量同步 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    bom_id = params.get("bom_id")
    material_id = params.get("material_id")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(
        BomDetail,
        Material.material_code,
        Material.material_name,
        Bom.bom_no,
    ).outerjoin(
        Material, BomDetail.material_id == Material.erp_material_id
    ).outerjoin(
        Bom, BomDetail.bom_id == Bom.bom_id
    )

    count_query = select(func.count()).select_from(BomDetail)

    if bom_id:
        query = query.where(BomDetail.bom_id == bom_id)
        count_query = count_query.where(BomDetail.bom_id == bom_id)

    if material_id:
        query = query.where(BomDetail.material_id == material_id)
        count_query = count_query.where(BomDetail.material_id == material_id)

    if updated_after:
        query = query.where(BomDetail.update_time >= updated_after)
        count_query = count_query.where(BomDetail.update_time >= updated_after)

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(BomDetail.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = (await db.execute(query)).all()

    items = [{
        "id": row.BomDetail.id,
        "bom_id": row.BomDetail.bom_id,
        "bom_no": row.bom_no,
        "line_no": row.BomDetail.line_no,
        "material_id": row.BomDetail.material_id,
        "material_code": row.material_code,
        "material_name": row.material_name,
        "standard_qty": float(row.BomDetail.standard_qty) if row.BomDetail.standard_qty is not None else None,
        "aux_qty": float(row.BomDetail.aux_qty) if row.BomDetail.aux_qty is not None else None,
        "material_type": row.BomDetail.material_type,
        "config_type": row.BomDetail.config_type,
        "lead_offset_days": row.BomDetail.lead_offset_days,
        "back_flush": row.BomDetail.back_flush,
        "scrap_rate": float(row.BomDetail.scrap_rate) if row.BomDetail.scrap_rate is not None else None,
        "oper_sn": row.BomDetail.oper_sn,
        "process_id": row.BomDetail.process_id,
        "warehouse_id": row.BomDetail.warehouse_id,
        "location_id": row.BomDetail.location_id,
        "valid_date": row.BomDetail.valid_date.isoformat() if row.BomDetail.valid_date else None,
        "invalid_date": row.BomDetail.invalid_date.isoformat() if row.BomDetail.invalid_date else None,
        "unit_id": row.BomDetail.unit_id,
        "customer_bom_code": row.BomDetail.customer_bom_code,
        "aux_attr_id": row.BomDetail.aux_attr_id,
        "material_size": row.BomDetail.material_size,
        "kit_flag": row.BomDetail.kit_flag,
        "data_source": row.BomDetail.data_source,
        "create_time": row.BomDetail.create_time.isoformat() if row.BomDetail.create_time else None,
        "update_time": row.BomDetail.update_time.isoformat() if row.BomDetail.update_time else None,
    } for row in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
