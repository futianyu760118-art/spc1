"""Tool: 查询产品 BOM 明细

根据物料编码查询产品的 BOM 及其明细：
1. 通过 material_code 关联 scm_material 取得 material_id；
2. 通过 material_id 关联 scm_bom 取得该产品的 BOM 列表；
3. 通过 bom_id 关联 scm_bom_detail 取得 BOM 明细行；
4. 明细中的子物料通过 material_id 关联 scm_material 反查物料编码/名称。
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.bom import Bom
from app.models.basicdata.bom_detail import BomDetail
from app.models.basicdata.material import Material
from app.services.assistant.tool_registry import register_tool

PARAMETERS = {
    "type": "object",
    "properties": {
        "material_code": {
            "type": "string",
            "description": "产品/父物料编码（精确匹配 scm_material.material_code），用于查询该产品的 BOM 及明细。",
        },
        "bom_no": {
            "type": "string",
            "description": "BOM编号（模糊匹配），可选筛选条件。",
        },
        "bom_version": {
            "type": "string",
            "description": "BOM版本号（精确匹配），可选筛选条件。",
        },
        "bom_type": {
            "type": "string",
            "description": "BOM类型（精确匹配），可选筛选条件。",
        },
        "use_status": {
            "type": "string",
            "description": "BOM使用状态（精确匹配），可选筛选条件。",
        },
        "include_details": {
            "type": "boolean",
            "description": "是否返回每个 BOM 的明细行，默认 true",
        },
        "limit": {
            "type": "integer",
            "description": "返回 BOM 条数上限，默认20",
        },
    },
    "required": ["material_code"],
}


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@register_tool(
    name="search_bom_details",
    description=(
        "查询产品的 BOM（物料清单）及明细。根据物料编码查询该产品的 BOM 列表，"
        "并返回每个 BOM 下的明细行（子物料编码、名称、标准用量、损耗率、工序、仓位等）。"
        "支持按 BOM编号、版本号、类型、使用状态筛选。"
    ),
    parameters=PARAMETERS,
    display_name="产品BOM查询",
    keywords=["BOM", "物料清单", "bom", "明细", "配方"],
    category="basicdata",
)
async def search_bom_details(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    material_code: Optional[str] = params.get("material_code")
    bom_no: Optional[str] = params.get("bom_no")
    bom_version: Optional[str] = params.get("bom_version")
    bom_type: Optional[str] = params.get("bom_type")
    use_status: Optional[str] = params.get("use_status")
    include_details: bool = bool(params.get("include_details", True))
    limit: int = int(params.get("limit", 20) or 20)

    if not material_code:
        return {"total": 0, "items": [], "error": "material_code 为必填参数"}

    # 1. 查询父物料主数据
    master_result = await db.execute(
        select(Material).where(Material.material_code == material_code)
    )
    master = master_result.scalars().first()
    if not master:
        return {"total": 0, "items": [], "error": f"未找到物料编码 {material_code}"}

    # 2. 查询该产品的 BOM 列表
    bom_query = select(Bom).where(Bom.material_id == master.material_id)
    count_query = select(func.count()).select_from(Bom).where(Bom.material_id == master.material_id)

    if bom_no:
        bom_query = bom_query.where(Bom.bom_no.ilike(f"%{bom_no}%"))
        count_query = count_query.where(Bom.bom_no.ilike(f"%{bom_no}%"))
    if bom_version:
        bom_query = bom_query.where(Bom.bom_version == bom_version)
        count_query = count_query.where(Bom.bom_version == bom_version)
    if bom_type:
        bom_query = bom_query.where(Bom.bom_type == bom_type)
        count_query = count_query.where(Bom.bom_type == bom_type)
    if use_status:
        bom_query = bom_query.where(Bom.use_status == use_status)
        count_query = count_query.where(Bom.use_status == use_status)

    total = (await db.execute(count_query)).scalar() or 0

    bom_query = bom_query.order_by(Bom.id.desc()).limit(limit)
    boms = (await db.execute(bom_query)).scalars().all()

    if not boms:
        return {
            "total": 0,
            "items": [],
            "material": {
                "material_code": master.material_code,
                "material_name": master.material_name,
                "spec_model": master.spec_model,
                "material_type": master.material_type,
                "unit_of_measure": master.unit_of_measure,
            },
        }

    # 3. 收集所有 bom_id，批量查询明细
    bom_ids = [b.bom_id for b in boms if b.bom_id]

    details_by_bom: Dict[str, List[Dict[str, Any]]] = {}
    if include_details and bom_ids:
        detail_result = await db.execute(
            select(
                BomDetail,
                Material.material_code,
                Material.material_name,
                Material.spec_model,
                Material.unit_of_measure,
            )
            .outerjoin(Material, BomDetail.material_id == Material.material_id)
            .where(BomDetail.bom_id.in_(bom_ids))
            .order_by(BomDetail.bom_id, BomDetail.line_no)
        )
        for row in detail_result.all():
            d = row[0]
            child_code = row[1]
            child_name = row[2]
            child_spec = row[3]
            child_unit = row[4]
            details_by_bom.setdefault(d.bom_id, []).append({
                "id": d.id,
                "line_no": d.line_no,
                "material_id": d.material_id,
                "material_code": child_code,
                "material_name": child_name,
                "spec_model": child_spec,
                "standard_qty": _to_float(d.standard_qty),
                "aux_qty": _to_float(d.aux_qty),
                "material_type": d.material_type,
                "config_type": d.config_type,
                "lead_offset_days": d.lead_offset_days,
                "back_flush": d.back_flush,
                "scrap_rate": _to_float(d.scrap_rate),
                "oper_sn": d.oper_sn,
                "process_id": d.process_id,
                "warehouse_id": d.warehouse_id,
                "location_id": d.location_id,
                "valid_date": _to_str(d.valid_date),
                "invalid_date": _to_str(d.invalid_date),
                "unit_id": d.unit_id,
                "unit_name": child_unit,
                "customer_bom_code": d.customer_bom_code,
                "aux_attr_id": d.aux_attr_id,
                "material_size": d.material_size,
                "kit_flag": d.kit_flag,
                "data_source": d.data_source,
                "create_time": _to_str(d.create_time),
                "update_time": _to_str(d.update_time),
            })

    # 4. 组装结果
    items: List[Dict[str, Any]] = []
    for b in boms:
        bom_item = {
            "type": "bom",
            "title": f"BOM {b.bom_no}",
            "subtitle": (
                f"产品 {master.material_code} {master.material_name or ''}"
                + (f" | 版本 {b.bom_version}" if b.bom_version else "")
                + (f" | 类型 {b.bom_type}" if b.bom_type else "")
            ).strip(" |"),
            "url": "/basic-data",
            "tags": [t for t in [b.bom_type, b.use_status] if t],
            # BOM 完整字段
            "bom_id": b.bom_id,
            "bom_no": b.bom_no,
            "material_id": b.material_id,
            "material_code": master.material_code,
            "material_name": master.material_name,
            "parent_material_id": b.parent_material_id,
            "bom_version": b.bom_version,
            "bom_type": b.bom_type,
            "bill_type_id": b.bill_type_id,
            "base_qty": _to_float(b.base_qty),
            "aux_attr_qty": _to_float(b.aux_attr_qty),
            "unit_id": b.unit_id,
            "aux_attr_id": b.aux_attr_id,
            "supply_mode": b.supply_mode,
            "customer_material_id": b.customer_material_id,
            "audit_status": b.audit_status,
            "use_status": b.use_status,
            "disabled_status": b.disabled_status,
            "void_flag": b.void_flag,
            "is_audited": b.is_audited,
            "audit_date": _to_str(b.audit_date),
            "entry_date": _to_str(b.entry_date),
            "data_source": b.data_source,
            "create_time": _to_str(b.create_time),
            "update_time": _to_str(b.update_time),
        }
        if include_details:
            details = details_by_bom.get(b.bom_id, [])
            bom_item["details"] = details
            bom_item["details_total"] = len(details)
        items.append(bom_item)

    return {
        "total": total,
        "items": items,
        "material": {
            "material_code": master.material_code,
            "material_name": master.material_name,
            "spec_model": master.spec_model,
            "material_type": master.material_type,
            "unit_of_measure": master.unit_of_measure,
            "brand": master.brand,
        },
    }
