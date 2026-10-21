"""执行面智能体工具 — 助手暴露给 LLM 的 3 个工具：查询 / 推理 / 订单写入。

- call_query_agent / call_reasoning_agent：只读，编排器直接执行；
- call_order_agent：写操作，编排器拦截生成「旧值 → 新值」确认单，人工确认后才派单（本模块不直接执行）。

能力边界全部来自 task_router 目录（与执行面 agent 契约同源）。
"""

import logging
import time
from typing import Any, Dict, List, Optional

from app.services.execution_agents import AGENT_SPECS, call_agent_run
from app.services.assistant.tool_registry import register_tool
from app.services.assistant.hub_reporter import now_iso, report_assistant_event
from app.services.assistant.task_router import (
    ORDER_ALLOWED_FIELDS,
    QUERY_CATALOG,
    REASONING_TASK_TYPES,
    validate_task_input,
)

logger = logging.getLogger(__name__)

AGENT_TOOL_LABELS = {
    "call_query_agent": "查询智能体",
    "call_reasoning_agent": "推理智能体",
    "call_order_agent": "订单智能体",
}

CAPABILITY_BY_TOOL = {
    "call_query_agent": "query_control_platform",
    "call_reasoning_agent": "reason_control_platform",
    "call_order_agent": "update_control_platform_order",
}

AGENT_KEY_BY_TOOL = {
    "call_query_agent": "query",
    "call_reasoning_agent": "reasoning",
    "call_order_agent": "order",
}

# 单步超时（沿用执行面派单超时：query 20s / reasoning 200s / order 30s）
TOOL_TIMEOUT_S = {
    "call_query_agent": 20.0,
    "call_reasoning_agent": 200.0,
    "call_order_agent": 30.0,
}

# 写确认前读取订单当前值的 4 个字段（与订单智能体字段白名单一致）
ORDER_READBACK_FIELDS = list(ORDER_ALLOWED_FIELDS)


def _query_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "enum": [c["path"] for c in QUERY_CATALOG],
                "description": "只读查询路径（白名单）",
            },
            "params": {
                "type": "object",
                "description": "查询参数，只放用户消息中可确定的筛选条件，不要编造",
            },
        },
        "required": ["path"],
    }


def _reasoning_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "task_type": {
                "type": "string",
                "enum": [c["type"] for c in REASONING_TASK_TYPES],
                "description": "分析任务类型",
            },
            "prompt": {"type": "string", "description": "要分析的问题"},
            "businessObjectRef": {
                "type": "string",
                "description": "业务对象锚点，格式 business://order/<订单号>（品质分析用 business://batch/<批次号>）",
            },
        },
        "required": ["task_type", "prompt", "businessObjectRef"],
    }


def _order_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "order_no": {"type": "string", "description": "销售订单号"},
            "fields": {
                "type": "object",
                "description": "要修改的字段，值必须是 YYYY-MM-DD 或 null（清空）；只允许白名单字段",
                "properties": {
                    field: {"type": ["string", "null"], "description": "YYYY-MM-DD 或 null"}
                    for field in ORDER_ALLOWED_FIELDS
                },
            },
        },
        "required": ["order_no", "fields"],
    }


def build_agent_tools_schema(include_order: bool = True, exclude: Optional[set] = None) -> List[Dict[str, Any]]:
    """生成 OpenAI function calling 工具清单；exclude 为运行时禁用工具名集合。"""
    excluded = exclude or set()
    specs = [
        {
            "name": "call_query_agent",
            "description": "调用查询智能体：中台只读查询（订单/物料/齐套/库存/供应商/品质/生产）。path 只能选白名单枚举。",
            "parameters": _query_tool_schema(),
        },
        {
            "name": "call_reasoning_agent",
            "description": "调用推理智能体：只读大模型分析（交期/齐套/品质/生产，带证据），耗时较长。",
            "parameters": _reasoning_tool_schema(),
        },
    ]
    if include_order:
        specs.append({
            "name": "call_order_agent",
            "description": "调用订单智能体：修改订单出货计划/发货完成/客户验货/上线时间。写操作不可撤销，执行前必须经用户确认，系统会先展示旧值→新值。",
            "parameters": _order_tool_schema(),
        })
    return [
        {"type": "function", "function": spec}
        for spec in specs
        if spec["name"] not in excluded
    ]


def normalize_tool_input(tool_name: str, args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把 LLM 工具入参归一化为执行面 agent 的派单入参。"""
    args = args if isinstance(args, dict) else {}
    if tool_name == "call_reasoning_agent":
        return {
            "prompt": args.get("prompt", ""),
            "task_type": args.get("task_type"),
            "context": {"businessObjectRef": args.get("businessObjectRef", "")},
            "constraints": {"read_only": True, "require_evidence": True},
        }
    if tool_name == "call_order_agent":
        return {"order_no": args.get("order_no", ""), "fields": args.get("fields") or {}}
    return {"path": args.get("path"), "params": args.get("params") or {}}


def validate_tool_input(tool_name: str, args: Optional[Dict[str, Any]]) -> Optional[str]:
    """校验 LLM 工具入参；合法返回 None，非法返回原因字符串。"""
    capability = CAPABILITY_BY_TOOL[tool_name]
    return validate_task_input(capability, normalize_tool_input(tool_name, args))


def _item_count(result: Any) -> int:
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        return len(result["items"])
    return 1 if result else 0


async def execute_agent_tool(
    tool_name: str,
    args: Dict[str, Any],
    *,
    operator_user_id: str = "",
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    """直接执行只读智能体工具（query / reasoning）。

    返回：{"ok", "online", "result", "error", "item_count"}
    - 参数非法 / agent 离线 / 繁忙 / 执行失败均返回 ok=False + error，绝不抛错。
    """
    capability = CAPABILITY_BY_TOOL[tool_name]
    task_input = normalize_tool_input(tool_name, args)
    invalid = validate_task_input(capability, task_input)
    if invalid:
        report_assistant_event(
            trace_id, "tool_result", tool_name, "failed", f"参数非法：{invalid}",
            {"params": args}, started_at=now_iso(),
            task_id=task_id, step_id=step_id, tool=tool_name,
        )
        return {"ok": False, "online": True, "result": None, "error": f"参数非法：{invalid}", "item_count": 0}

    started_at = now_iso()
    loop_start = time.perf_counter()
    report_assistant_event(
        trace_id, "tool_call", tool_name, "started",
        f"调用{AGENT_TOOL_LABELS[tool_name]}", {"input": task_input}, started_at=started_at,
        task_id=task_id, step_id=step_id, tool=tool_name,
    )
    dispatch = await call_agent_run(
        AGENT_SPECS[AGENT_KEY_BY_TOOL[tool_name]],
        task_input,
        timeout=TOOL_TIMEOUT_S[tool_name],
        operator_user_id=operator_user_id,
    )
    duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
    if not dispatch.get("online"):
        error = f"{AGENT_TOOL_LABELS[tool_name]}不可用：{dispatch.get('reason')}"
    elif dispatch.get("busy"):
        error = f"{AGENT_TOOL_LABELS[tool_name]}繁忙：{dispatch.get('reason')}"
    elif not dispatch.get("ok"):
        error = f"{AGENT_TOOL_LABELS[tool_name]}执行失败：{dispatch.get('reason')}"
    else:
        error = None

    if error:
        report_assistant_event(
            trace_id, "tool_result", tool_name, "failed", error[:200],
            {"input": task_input}, started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool=tool_name,
        )
        return {"ok": False, "online": bool(dispatch.get("online")), "result": None, "error": error, "item_count": 0}

    result = dispatch.get("result")
    report_assistant_event(
        trace_id, "tool_result", tool_name, "completed", f"返回 {_item_count(result)} 条",
        {"itemCount": _item_count(result)}, started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
        task_id=task_id, step_id=step_id, tool=tool_name,
    )
    return {"ok": True, "online": True, "result": result, "error": None, "item_count": _item_count(result)}


async def query_order_current_fields(
    order_no: str, *, operator_user_id: str = "", trace_id: str = "",
    task_id: Optional[str] = None, step_id: Optional[int] = None,
) -> Dict[str, Any]:
    """写确认前经查询智能体读取订单当前值（4 个可写字段）。

    返回 {"values": {field: value|None}, "missing": bool, "error": str|None}
    - missing=True 表示未能读到旧值（agent 离线 / 订单不存在 / 接口未返回字段）。
    """
    outcome = await execute_agent_tool(
        "call_query_agent",
        {"path": "/external/orders/list", "params": {"keyword": order_no, "page_size": 100}},
        operator_user_id=operator_user_id,
        trace_id=trace_id,
        task_id=task_id,
        step_id=step_id,
    )
    if not outcome.get("ok"):
        return {"values": {f: None for f in ORDER_READBACK_FIELDS}, "missing": True, "error": outcome.get("error")}
    items = (outcome.get("result") or {}).get("items") or []
    matched = next((it for it in items if str(it.get("order_no") or "") == order_no), None)
    if not matched:
        return {"values": {f: None for f in ORDER_READBACK_FIELDS}, "missing": True, "error": f"未查到订单 {order_no}"}
    values = {f: matched.get(f) for f in ORDER_READBACK_FIELDS}
    missing = any(f not in matched for f in ORDER_READBACK_FIELDS)
    return {"values": values, "missing": missing, "error": None}


async def _noop_execute(db=None, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """注册表占位执行体：编排器不经过注册表执行智能体工具，只经 build_agent_tools_schema 下发。"""
    return {"error": "执行面智能体工具由编排器统一执行，不经过注册表直接调用"}


def register_agent_tools() -> None:
    """把 3 个智能体工具注册进全局注册表（/tools、/skills、禁用校验、{{TOOLS}} 占位符用）。"""
    register_tool(
        "call_query_agent",
        "调用查询智能体：中台只读查询（订单/物料/齐套/库存/供应商/品质/生产）",
        _query_tool_schema(),
        display_name="查询智能体",
        keywords=["查询", "订单", "物料", "齐套", "库存"],
        category="agent",
        read_only=True,
    )(_noop_execute)
    register_tool(
        "call_reasoning_agent",
        "调用推理智能体：只读大模型分析（交期/齐套/品质/生产，带证据）",
        _reasoning_tool_schema(),
        display_name="推理智能体",
        keywords=["分析", "风险", "交期"],
        category="agent",
        read_only=True,
    )(_noop_execute)
    register_tool(
        "call_order_agent",
        "调用订单智能体：修改订单出货计划/发货完成/客户验货/上线时间（执行前需用户确认）",
        _order_tool_schema(),
        display_name="订单智能体",
        keywords=["修改", "写入", "出货计划", "交期"],
        category="agent",
        read_only=False,
        requires_confirmation=True,
    )(_noop_execute)


register_agent_tools()
