"""助手任务能力目录与入参校验 — 编排器 ReAct 循环的唯一能力边界来源。

能力目录与执行面 agent 契约同源（变更需三处同步）：
- query 白名单 = agents/query-agent/src/query-adapter.js PATH_ENDPOINT_CODES（契约 §4.2，已排除 int:health.ping）
- reasoning 任务类型 = agents/reasoning-agent/src/reasoning-adapter.js inputSchema
- order 字段白名单 = agents/order-agent/src/order-adapter.js ALLOWED_FIELDS

仅保留能力目录与校验；分类 / 派单 / 渲染已随 AI 自主 ReAct 方案移除。
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

QUERY_CATALOG: List[Dict[str, str]] = [
    {"path": "/external/orders/list", "name": "销售订单列表",
     "params": "order_no(订单号精确),keyword(订单号/客户/产品名模糊),status(逗号多选:pending_review/in_progress/partially_closed/completed/cancelled),customer_code,risk_level(red/yellow),promised_date_start,promised_date_end,page,page_size"},
    {"path": "/external/order-details/list", "name": "订单明细行",
     "params": "order_no,keyword,product_code,status(open/closed),bom_no,promised_date_start,promised_date_end,page,page_size"},
    {"path": "/external/boms/tree", "name": "产品 BOM 多级树",
     "params": "bom_id(必填,根BOM的id),demand_qty(需求数量),flatten(true返回平铺)"},
    {"path": "/external/materials/list", "name": "物料列表",
     "params": "keyword(物料编码/名称/规格型号),material_type,is_purchase(0/1),is_produce(0/1),status(1启用0停用),page,page_size"},
    {"path": "/external/suppliers/list", "name": "供应商列表",
     "params": "keyword(供应商编码/名称/简称),supplier_type,status(1启用0停用),page,page_size"},
    {"path": "/external/material-kitting/results", "name": "齐套结果",
     "params": "demand_type(SALES_ORDER),demand_no(订单号),demand_line_no,kit_status(FULL/PARTIAL/SHORTAGE/BLOCKED/PENDING),risk_level(green/yellow/red),required_date_start,required_date_end,page,page_size"},
    {"path": "/external/material-kitting/shortages", "name": "缺料明细",
     "params": "demand_no(订单号),material_code,is_key_material,alert_status,page,page_size"},
    {"path": "/external/material-kitting/demands", "name": "齐套需求(订单维度)",
     "params": "order_no,customer_code,product_code,page,page_size"},
    {"path": "/external/inventory/availability", "name": "库存可用量",
     "params": "material_code,keyword,wh_code(仓库),page,page_size"},
    {"path": "/external/material-supplies/list", "name": "物料供给(采购/委外/生产/调拨)",
     "params": "material_code,supply_type(PURCHASE/OUTSOURCE/PRODUCTION/TRANSFER),supply_no,expected_date_start,expected_date_end,page,page_size"},
    {"path": "/external/quality-issues/list", "name": "品质异常列表",
     "params": "issue_no,order_no,product_code,status(open/in_progress/closed),defect_type,submit_dept,occurred_start,occurred_end,page,page_size"},
    {"path": "/external/quality-trace/list", "name": "质量追溯",
     "params": "order_no,product_code,batch_no,page,page_size"},
    {"path": "/external/production/work-orders/list", "name": "生产工单列表",
     "params": "work_order_no,order_no,product_code,status,workshop,planned_end_start,planned_end_end,page,page_size"},
    {"path": "/external/production/operations/list", "name": "工序进度",
     "params": "order_no,process_type(前道/贴片/组装/包装/装配),status,plan_date_start,plan_date_end,page,page_size"},
    {"path": "/external/production/order-links/list", "name": "订单-工单关联",
     "params": "work_order_no,order_no,link_type(production_task/schedule_snapshot),page,page_size"},
    {"path": "/external/production/reports/list", "name": "生产日报",
     "params": "work_order_no,order_no,report_date_start,report_date_end,page,page_size"},
    {"path": "/external/production/capacity/list", "name": "产能占用",
     "params": "department,schedule_bucket(lean/assembly/packaging),date_start,date_end,page,page_size"},
]

REASONING_TASK_TYPES = [
    {"type": "order_delivery_analysis", "desc": "订单交期/交付风险分析（业务锚点 business://order/<订单号>）"},
    {"type": "material_kitting_analysis", "desc": "齐套/缺料分析（业务锚点 business://order/<订单号>）"},
    {"type": "quality_analysis", "desc": "品质分析（业务锚点 business://batch/<批次号>）"},
    {"type": "production_analysis", "desc": "生产分析（业务锚点 business://order/<订单号>）"},
]

ORDER_FIELDS_DOC = (
    "shipping_plan 出货计划(YYYY-MM-DD或null清空), delivery_completed_date 发货完成时间, "
    "customer_inspection_date 客户验货时间, planned_start_date 上线时间"
)

ORDER_ALLOWED_FIELDS = (
    "shipping_plan",
    "delivery_completed_date",
    "customer_inspection_date",
    "planned_start_date",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BUSINESS_REF_RE = re.compile(r"^business://(order|product|batch)/\S+$")


def validate_task_input(capability: str, task_input: Optional[Dict[str, Any]]) -> Optional[str]:
    """校验编排器产出的智能体入参；合法返回 None，非法返回原因字符串。"""
    if not isinstance(task_input, dict):
        return "input 必须是对象"
    if capability == "query_control_platform":
        path = task_input.get("path")
        if path not in {c["path"] for c in QUERY_CATALOG}:
            return f"path 不在白名单: {path}"
        params = task_input.get("params")
        if params is not None and not isinstance(params, dict):
            return "params 必须是对象"
        return None
    if capability == "reason_control_platform":
        if not (task_input.get("prompt") or "").strip():
            return "prompt 不能为空"
        if task_input.get("task_type") not in {c["type"] for c in REASONING_TASK_TYPES}:
            return f"task_type 不在枚举: {task_input.get('task_type')}"
        context = task_input.get("context")
        ref = (context or {}).get("businessObjectRef", "") if isinstance(context, dict) else ""
        if not _BUSINESS_REF_RE.match(ref or ""):
            return "context.businessObjectRef 缺失或格式错误（须 business://order|product|batch/<键>）"
        return None
    if capability == "update_control_platform_order":
        if not (task_input.get("order_no") or "").strip():
            return "order_no 不能为空"
        fields = task_input.get("fields")
        if not isinstance(fields, dict) or not fields:
            return "fields 至少一个字段"
        for key, value in fields.items():
            if key not in ORDER_ALLOWED_FIELDS:
                return f"字段不在白名单: {key}"
            if value is not None and (not isinstance(value, str) or not _DATE_RE.match(value)):
                return f"字段 {key} 必须是 YYYY-MM-DD 或 null"
        return None
    return f"未知 capability: {capability}"


def trim_result(
    result: Dict[str, Any], max_items: int = 20, max_chars: int = 8000
) -> Dict[str, Any]:
    """结构化裁剪执行结果：保留元数据、items 取前 N 条并按序列化长度收缩，保证 JSON 合法。"""
    if not isinstance(result, dict):
        return result
    items = result.get("items")
    if not isinstance(items, list) or not items:
        return result
    trimmed_items = items[:max_items]
    trimmed = {**result, "items": trimmed_items}
    if len(items) > len(trimmed_items):
        trimmed["_items_truncated"] = True
        trimmed["_items_shown"] = len(trimmed_items)
    while trimmed_items and len(json.dumps(trimmed, ensure_ascii=False, default=str)) > max_chars:
        trimmed_items = trimmed_items[:-1]
        trimmed = {**trimmed, "items": trimmed_items, "_items_truncated": True, "_items_shown": len(trimmed_items)}
    return trimmed
