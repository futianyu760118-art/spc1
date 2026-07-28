"""Tool: 查询订单齐套信息

基于物料齐套分析服务，按销售订单号查询齐套状态及物料明细。
- 当传入 order_no 时，既返回该订单的齐套汇总，也返回展开后的物料明细；
- 当未传 order_no 时，返回按订单聚合的齐套列表（支持风险等级、订单类型等筛选）。
"""

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.assistant.tool_registry import register_tool
from app.services.material.kit_analysis_service import get_kit_analysis, get_order_materials

PARAMETERS = {
    "type": "object",
    "properties": {
        "order_no": {
            "type": "string",
            "description": "销售订单号（精确或模糊匹配，如 HJ202604-0018-0086）。传入后会同时返回该订单的齐套汇总和物料明细。",
        },
        "order_type": {
            "type": "string",
            "description": "订单类型筛选，多选逗号分隔：big（大单，HJ开头）, sample（样品单，HJY开头）",
        },
        "risk_level": {
            "type": "string",
            "enum": ["red", "yellow", "green"],
            "description": "齐套风险等级: red=齐套率低于80%, yellow=齐套率80%-99%, green=齐套率100%",
        },
        "only_pending_shipment": {
            "type": "boolean",
            "description": "是否只查发货未完成的订单，默认 false",
        },
        "promised_date_start": {
            "type": "string",
            "description": "合同交期开始日期 YYYY-MM-DD",
        },
        "promised_date_end": {
            "type": "string",
            "description": "合同交期结束日期 YYYY-MM-DD",
        },
        "include_materials": {
            "type": "boolean",
            "description": "是否返回订单展开后的物料明细（仅在传入 order_no 时生效），默认 true",
        },
        "limit": {
            "type": "integer",
            "description": "齐套列表返回条数上限，默认20",
        },
    },
    "required": [],
}


def _item_to_dict(item: Any) -> Dict[str, Any]:
    """将 KitAnalysisItem / KitAnalysisMaterialItem 转为可序列化字典"""
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    return dict(item)


@register_tool(
    name="search_kit_analysis",
    description=(
        "查询销售订单的物料齐套信息。可根据订单编号查询齐套率、已到齐/部分到/未下单/逾期/呆滞物料数量，"
        "以及展开后的物料明细（含采购下单、收料、ETA、状态等）。支持按订单类型、齐套风险等级、交期范围筛选。"
    ),
    parameters=PARAMETERS,
    display_name="订单齐套查询",
    keywords=["齐套", "kit", "齐套率", "欠料", "订单物料"],
    category="material",
)
async def search_kit_analysis(db: AsyncSession, params: Dict[str, Any]) -> Dict[str, Any]:
    order_no: Optional[str] = params.get("order_no")
    order_type: Optional[str] = params.get("order_type")
    risk_level: Optional[str] = params.get("risk_level")
    only_pending_shipment: bool = bool(params.get("only_pending_shipment", False))
    promised_date_start: Optional[str] = params.get("promised_date_start")
    promised_date_end: Optional[str] = params.get("promised_date_end")
    include_materials: bool = bool(params.get("include_materials", True))
    limit: int = int(params.get("limit", 20) or 20)

    # 按订单聚合的齐套列表
    kit_result = await get_kit_analysis(
        db,
        order_no=order_no,
        order_type=order_type,
        risk_level=risk_level,
        only_pending_shipment=only_pending_shipment,
        promised_date_start=promised_date_start,
        promised_date_end=promised_date_end,
        page=1,
        page_size=limit,
    )

    kit_items = [_item_to_dict(item) for item in kit_result.get("items", [])]
    statistics = kit_result.get("statistics", {})
    total = kit_result.get("total", 0)

    items: list = []
    for kit_item in kit_items:
        entry: Dict[str, Any] = {
            "type": "kit_analysis",
            "title": f"订单 {kit_item.get('order_no')} 齐套率 {int(kit_item.get('kit_rate', 0) * 100)}%",
            "subtitle": (
                f"已到齐 {kit_item.get('received_materials', 0)}/{kit_item.get('total_materials', 0)}"
                f" | 未下单 {kit_item.get('not_ordered_materials', 0)}"
                f" | 逾期 {kit_item.get('overdue_materials', 0)}"
                f" | 呆滞 {kit_item.get('stagnant_materials', 0)}"
            ),
            "url": "/material-kit",
            "tags": [kit_item.get("risk_level")] if kit_item.get("risk_level") else [],
        }
        entry.update(kit_item)
        items.append(entry)

    result: Dict[str, Any] = {
        "total": total,
        "items": items,
        "statistics": statistics,
    }

    # 若指定了订单号且需要物料明细，则展开该订单的物料明细
    if order_no and include_materials:
        try:
            material_items = await get_order_materials(db, order_no=order_no)
        except Exception:
            material_items = []

        materials: list = []
        for m in material_items:
            m_dict = _item_to_dict(m)
            entry = {
                "type": "kit_material",
                "title": f"{m_dict.get('material_code', '')} {m_dict.get('material_name') or ''}".strip(),
                "subtitle": (
                    f"状态: {m_dict.get('status_label') or m_dict.get('status', '')}"
                    f" | 下单 {m_dict.get('po_qty') if m_dict.get('po_qty') is not None else 0}"
                    f" | 收料 {m_dict.get('received_qty') if m_dict.get('received_qty') is not None else 0}"
                ),
                "url": "/material-kit",
                "tags": [
                    t for t in [
                        m_dict.get("status_label"),
                        m_dict.get("bill_type_label"),
                    ] if t
                ] + (["呆滞"] if m_dict.get("is_stagnant") else []),
            }
            entry.update(m_dict)
            materials.append(entry)

        result["materials"] = materials
        result["materials_total"] = len(materials)

    return result
