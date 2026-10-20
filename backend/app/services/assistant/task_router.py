"""助手任务路由 — 判定用户任务能否由本系统执行面智能体完成，命中即本地派单。

能力目录与执行面 agent 契约同源（变更需三处同步）：
- query 白名单 = agents/query-agent/src/query-adapter.js PATH_ENDPOINT_CODES（契约 §4.2，已排除 int:health.ping）
- reasoning 任务类型 = agents/reasoning-agent/src/reasoning-adapter.js inputSchema
- order 字段白名单 = agents/order-agent/src/order-adapter.js ALLOWED_FIELDS

分类/派单/渲染任何失败均 fail-safe：不阻断助手主流程。
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.services.ai import ChatMessage, ChatOptions, ai_service
from app.services.execution_agents import AGENT_SPECS, call_agent_run

logger = logging.getLogger(__name__)

CAPABILITY_TO_AGENT = {
    "query_control_platform": "query",
    "reason_control_platform": "reasoning",
    "update_control_platform_order": "order",
}

DISPATCH_TIMEOUT_S = {"query": 20.0, "order": 30.0, "reasoning": 200.0}

QUERY_CATALOG: List[Dict[str, str]] = [
    {"path": "/external/orders/list", "name": "销售订单列表",
     "params": "keyword(订单号/客户/产品名模糊),status(逗号多选:pending_review/in_progress/partially_closed/completed/cancelled),customer_code,risk_level(red/yellow),promised_date_start,promised_date_end,page,page_size"},
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


class RoutingClassification(BaseModel):
    """路由分类结果（LLM structured_output 产出）"""

    decision: str = Field(
        ...,
        description="local=本地执行面可完成；hub=本地不能完成、需发布 Hub；none=非任务闲聊",
    )
    capability: Optional[str] = Field(
        None,
        description="decision=local 时必填：query_control_platform | reason_control_platform | update_control_platform_order",
    )
    input: Optional[Dict[str, Any]] = Field(None, description="decision=local 时必填：对应能力的派单入参")
    reason: str = Field("", description="判定理由（一句话）")


def _build_classification_prompt(message: str, history: List[Dict[str, Any]]) -> str:
    lines = [
        "你是供应链中台的智能任务路由器。判断用户最新消息是否是一个任务，以及本系统执行面智能体能否完成它。",
        "",
        "本系统执行面智能体能力目录：",
        "",
        "1) query_control_platform（查询智能体）——中台只读查询，path 白名单：",
    ]
    for item in QUERY_CATALOG:
        lines.append(f"- {item['path']}：{item['name']}；可用参数 {item['params']}")
    lines += [
        "",
        "2) reason_control_platform（推理智能体）——只读大模型分析（带证据），task_type 枚举：",
    ]
    for item in REASONING_TASK_TYPES:
        lines.append(f"- {item['type']}：{item['desc']}")
    lines += [
        "   input 格式：{\"prompt\": 分析问题, \"task_type\": 上述枚举, "
        "\"context\": {\"businessObjectRef\": \"business://order|product|batch/<键>\"}, "
        "\"constraints\": {\"read_only\": true, \"require_evidence\": true}}",
        "",
        "3) update_control_platform_order（订单智能体）——写能力，字段白名单：" + ORDER_FIELDS_DOC,
        "   input 格式：{\"order_no\": 销售订单号, \"fields\": {字段: \"YYYY-MM-DD\"或null}}，至少一个字段",
        "",
        "判定规则：",
        "- 用户要求查询订单/物料/库存/齐套/供应商/品质/生产数据 → local，capability=query_control_platform，"
        "input.path 从白名单选最贴切的一个，input.params 只放消息中可确定的筛选条件",
        "- 用户要求分析交期/齐套/品质/生产（需要结论与建议，而非简单罗列）→ local，capability=reason_control_platform，"
        "task_type 选最贴切的枚举，businessObjectRef 用消息中的订单号/产品编码/批次号",
        "- 用户要求修改订单的出货计划/发货完成/客户验货/上线时间 → local，capability=update_control_platform_order，"
        "fields 只放消息中明确提到的字段与日期",
        "- 消息里没有订单号/物料编码等具体对象、但明确要求查询清单 → local，query_control_platform，params 只放明确条件",
        "- 是任务但无法用以上任一能力完成（如改物料、发消息、写文档、跨系统协作）→ hub",
        "- 纯闲聊/感谢/自我介绍（你好、谢谢、你能做什么）→ none",
        "- 日期优先转 YYYY-MM-DD；参数值不得编造，消息中未提供的具体编号不要填",
    ]
    if history:
        lines.append("")
        lines.append("最近对话历史（用于理解指代，如“这个订单”）：")
        for msg in history[-6:]:
            role = msg.get("role")
            content = str(msg.get("content", ""))[:200]
            if role in ("user", "assistant") and content:
                lines.append(f"{'用户' if role == 'user' else '助手'}: {content}")
    lines.append("")
    lines.append(f"用户最新消息：{message}")
    return "\n".join(lines)


def validate_task_input(capability: str, task_input: Optional[Dict[str, Any]]) -> Optional[str]:
    """校验分类产出的派单入参；合法返回 None，非法返回原因字符串。"""
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


async def classify_task(
    message: str,
    history: List[Dict[str, Any]],
    model_override: Optional[str] = None,
) -> RoutingClassification:
    """LLM 分类；任何失败 fail-safe 返回 decision=none。"""
    try:
        options = ChatOptions(temperature=0.0, max_tokens=600, model=model_override, timeout=30)
        result = await ai_service.structured_output(
            _build_classification_prompt(message, history), RoutingClassification, options
        )
        if result.decision not in ("local", "hub", "none"):
            result.decision = "none"
        return result
    except Exception as e:
        logger.warning(f"[task_router] 路由分类失败: {e}")
        return RoutingClassification(decision="none", reason=f"分类失败: {str(e)[:120]}")


async def dispatch_local(
    agent_key: str, task_input: Dict[str, Any], operator_user_id: str = ""
) -> Dict[str, Any]:
    """本地派单到执行面 agent（POST /admin/run）；失败不抛错，返回归一化结果。"""
    return await call_agent_run(
        AGENT_SPECS[agent_key],
        task_input,
        timeout=DISPATCH_TIMEOUT_S.get(agent_key, 30.0),
        operator_user_id=operator_user_id,
    )


async def route_task(
    message: str,
    history: List[Dict[str, Any]],
    model_override: Optional[str] = None,
    operator_user_id: str = "",
) -> Dict[str, Any]:
    """路由步骤：分类 → 校验 → 本地派单（如命中）。

    返回：
    {
      "decision": "local"|"hub"|"none",
      "capability": str|None, "agent_key": str|None, "agent_label": str|None,
      "reason": str, "executed": bool, "dispatch_error": str|None,
      "result": dict|None, "classification": dict|None,
    }
    命中本地但 agent 离线/繁忙/执行失败时 decision 降级为 hub，dispatch_error 记原因。
    """
    outcome: Dict[str, Any] = {
        "decision": "none",
        "capability": None,
        "agent_key": None,
        "agent_label": None,
        "reason": "",
        "executed": False,
        "dispatch_error": None,
        "result": None,
        "classification": None,
    }
    classification = await classify_task(message, history, model_override)
    outcome["classification"] = classification.model_dump()
    decision = classification.decision
    if decision != "local":
        if decision == "hub":
            outcome["decision"] = "hub"
            outcome["reason"] = classification.reason or "本地执行面无匹配能力"
        return outcome

    capability = classification.capability
    agent_key = CAPABILITY_TO_AGENT.get(capability or "")
    if not agent_key:
        outcome["decision"] = "hub"
        outcome["reason"] = f"分类产出未知 capability: {capability}"
        return outcome
    spec = AGENT_SPECS[agent_key]
    outcome.update(
        decision="local",
        capability=capability,
        agent_key=agent_key,
        agent_label=spec.label,
        reason=classification.reason,
    )
    invalid = validate_task_input(capability, classification.input)
    if invalid:
        outcome["decision"] = "hub"
        outcome["reason"] = f"本地能力匹配但参数无效：{invalid}"
        outcome["dispatch_error"] = invalid
        return outcome
    dispatch = await dispatch_local(agent_key, classification.input or {}, operator_user_id=operator_user_id)
    if dispatch.get("online") and dispatch.get("ok"):
        outcome["executed"] = True
        outcome["result"] = dispatch.get("result") or {}
        return outcome
    outcome["decision"] = "hub"
    outcome["dispatch_error"] = dispatch.get("reason") or "派单失败"
    outcome["reason"] = f"本地智能体不可用：{outcome['dispatch_error']}"
    return outcome


_RENDER_ROUTE_RESULT_PROMPT = """你是供应链与生产协同中台的智能决策助手。执行面智能体（{agent_label}）已为用户完成任务，请根据执行结果整理 Markdown 回复：
- 结果含 items 列表时：必须用 Markdown 表格逐条列出所有给到的数据行（订单号、客户、产品、数量、状态、风险、交期等关键字段），不得省略、不得只写条数
- 结果不含 items（单对象/结论）时：用要点列出关键信息
- 用 **加粗** 标注关键信息（订单号、数量、日期、风险等级、结论）
- 结果标注 _items_truncated=true 时，表格后注明"仅展示前 N 条，共 total 条"
- 控制在 800 字以内；不要输出 <think> 标签；不要臆造结果中不存在的数据

用户原始请求：{message}

执行结果（JSON）：
{result_json}"""


def _trim_result_for_render(
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


async def render_route_result(
    message: str,
    agent_label: str,
    result: Dict[str, Any],
    model_override: Optional[str] = None,
) -> str:
    """把本地执行结果渲染为面向用户的 Markdown 回复；失败返回兜底文本。"""
    prompt = _RENDER_ROUTE_RESULT_PROMPT.format(
        agent_label=agent_label,
        message=message,
        result_json=json.dumps(_trim_result_for_render(result), ensure_ascii=False, default=str),
    )
    try:
        options = ChatOptions(temperature=0.1, max_tokens=2500, model=model_override, timeout=90)
        raw = await ai_service.chat([ChatMessage(role="user", content=prompt)], options)
        text = raw if isinstance(raw, str) else (raw.text or "")
        return text.strip() or "任务已完成，但结果整理失败。"
    except Exception as e:
        logger.warning(f"[task_router] 结果渲染失败: {e}")
        return "任务已完成，但结果整理失败。"
