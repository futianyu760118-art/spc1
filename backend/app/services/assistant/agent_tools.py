"""执行面智能体工具 — 助手暴露给 LLM 的工具：查询 / 推理 / 订单写入 / Hub 外部查询。

- call_query_agent / call_reasoning_agent：只读，编排器直接执行；
- call_order_agent：写操作，编排器拦截生成「旧值 → 新值」确认单，人工确认后才派单（本模块不直接执行）；
- hub_query：跨系统只读查询，不经执行面 agent，直接走 hub_client（发起 + 轮询借调单）。

能力边界来自 task_router 目录（与执行面 agent 契约同源）；hub_query 边界来自 Hub 能力目录。
"""

import base64
import io
import logging
import mimetypes
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.storage import get_storage

from app.core.audit import log_audit
from app.core.config import get_settings
from app.core.security import check_permission
from app.services.agent.capabilities import allowed_skill_admin_tools
from app.services.agent.errors import AgentError
from app.services.agent.skill_executors import (
    SkillExecutorContext,
    get_skill_executor,
    run_skill_executor as run_registered_executor,
    validate_executor_for_member,
)
from app.services.agent.skill_sandbox import is_sandbox_enabled, run_skill_script as run_sandbox_script
from app.services.agent.skills import (
    create_skill_from_content,
    get_skill_for_user,
    install_skill_from_url,
    install_skillhub_pack,
    install_skillhub_skill,
    load_skill_content,
    read_skill_text_file,
    resolve_skill_for_manage,
    uninstall_skill_with_pack,
    uninstall_skillhub_pack,
)
from app.services.execution_agents import AGENT_SPECS, call_agent_run
from app.services.hub_client import (
    capability_names,
    is_hub_enabled,
    provider_system,
    query_and_poll,
    validate_capability,
)
from app.services.assistant.tool_registry import register_tool
from app.services.assistant.hub_reporter import now_iso, report_assistant_event
from app.services.order.write_registry import (
    ASSISTANT_FIELDS,
    ASSISTANT_OPERATIONS,
    DEFAULT_ASSISTANT_OPERATION,
)
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
    "hub_query": "Hub 外部查询",
    "create_feedback": "创建问题反馈",
    "revoke_feedback": "撤销问题反馈",
    "use_skill": "团队技能",
    "read_skill_file": "技能资源",
    "run_skill_script": "技能脚本",
    "run_skill_executor": "技能执行器",
    "create_skill": "创建技能",
    "install_skill": "安装技能",
    "uninstall_skill": "卸载技能",
}

FEEDBACK_TOOLS = ("create_feedback", "revoke_feedback")
SKILL_TOOLS = ("use_skill", "read_skill_file", "run_skill_script", "run_skill_executor")
ADMIN_SKILL_TOOLS = ("create_skill", "install_skill", "uninstall_skill")
RUNTIME_SKILL_FILE_MAX_BYTES = 64 * 1024

CAPABILITY_BY_TOOL = {
    "call_query_agent": "query_control_platform",
    "call_reasoning_agent": "reason_control_platform",
    "call_order_agent": "write_control_platform",
    "hub_query": "hub_query",
    "create_feedback": "feedback_control_platform",
    "revoke_feedback": "feedback_control_platform",
}

AGENT_KEY_BY_TOOL = {
    "call_query_agent": "query",
    "call_reasoning_agent": "reasoning",
    "call_order_agent": "order",
}

# 单步超时（沿用执行面派单超时：query 20s / reasoning 200s / order 30s；hub_query 30s 轮询收口）
TOOL_TIMEOUT_S = {
    "call_query_agent": 20.0,
    "call_reasoning_agent": 200.0,
    "call_order_agent": 30.0,
    "hub_query": 30.0,
}

# 写确认前读取订单当前值的字段（注册表 assistant 操作字段白名单）
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
            "member_id": {
                "type": "integer",
                "description": "团队内承接该任务的智能体编号；同能力仅一个成员时可省略",
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
            "member_id": {
                "type": "integer",
                "description": "团队内承接该任务的智能体编号；同能力仅一个成员时可省略",
            },
        },
        "required": ["task_type", "prompt", "businessObjectRef"],
    }


def _order_tool_titles() -> str:
    return "、".join(op["title"] for op in ASSISTANT_OPERATIONS)


def _order_tool_description() -> str:
    return (
        f"调用订单智能体：{_order_tool_titles()}。"
        "写操作不可撤销，执行前必须经用户确认，系统会先展示旧值→新值。"
    )


def _order_tool_schema(allowed_fields: Optional[set] = None) -> Dict[str, Any]:
    fields = [
        field for field in ASSISTANT_FIELDS
        if allowed_fields is None or field["wire"] in allowed_fields
    ]
    field_properties = {
        field["wire"]: {"type": ["string", "null"], "description": "YYYY-MM-DD 或 null"}
        for field in fields
    }
    operation_labels = "；".join(
        f"{op['name']}（{op['title']}）" for op in ASSISTANT_OPERATIONS
    )
    return {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [op["name"] for op in ASSISTANT_OPERATIONS],
                "description": f"写操作类型：{operation_labels}",
            },
            "order_no": {"type": "string", "description": "销售订单号"},
            "fields": {
                "type": "object",
                "description": "要修改的字段，值必须是 YYYY-MM-DD 或 null（清空）；只允许白名单字段",
                "properties": field_properties,
            },
        },
        "required": ["operation", "order_no", "fields"],
    }


def _hub_query_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "capability": {
                "type": "string",
                "enum": capability_names(),
                "description": "外部系统查询能力（Hub 能力目录白名单，不含本系统；当前仅 query_plm：查询 PLM 研发项目）",
            },
            "params": {
                "type": "object",
                "description": "能力参数（query_plm 支持 keyword：项目号或关键字），只放用户消息中可确定的值，不要编造",
            },
        },
        "required": ["capability"],
    }


def _feedback_create_tool_schema() -> Dict[str, Any]:
    from app.services.basicdata.feedback_service import (
        FEEDBACK_DESCRIPTION_MAX,
        FEEDBACK_SEVERITIES,
        FEEDBACK_TITLE_MAX,
        FEEDBACK_TYPES,
    )
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": f"反馈标题（必填，不超过 {FEEDBACK_TITLE_MAX} 字）"},
            "description": {"type": "string", "description": f"问题/建议的详细描述（必填，不超过 {FEEDBACK_DESCRIPTION_MAX} 字）"},
            "type": {
                "type": "string",
                "enum": list(FEEDBACK_TYPES),
                "description": "反馈类型：issue=问题，suggestion=建议，inquiry=咨询（默认 issue）",
            },
            "severity": {
                "type": "string",
                "enum": list(FEEDBACK_SEVERITIES),
                "description": "严重程度（默认 low）",
            },
        },
        "required": ["title", "description"],
    }


def _feedback_revoke_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "feedback_id": {"type": "integer", "description": "要撤销的反馈编号（仅本人待处理的反馈可撤销）"},
        },
        "required": ["feedback_id"],
    }


def _use_skill_tool_schema(skills: List[Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "integer",
                "enum": [int(skill.skill_id) for skill in skills],
                "description": "技能编号（见系统提示【团队技能】）",
            },
        },
        "required": ["skill_id"],
    }


def _read_skill_file_tool_schema(skills: List[Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "integer",
                "enum": [int(skill.skill_id) for skill in skills],
                "description": "技能编号（须先用 use_skill 加载）",
            },
            "path": {
                "type": "string",
                "description": "技能文件清单中的相对路径，如 references/guide.md",
            },
        },
        "required": ["skill_id", "path"],
    }


def _run_skill_script_tool_schema(skills: List[Any]) -> Dict[str, Any]:
    script_skill_ids = [int(skill.skill_id) for skill in skills if skill.has_scripts]
    return {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "integer",
                "enum": script_skill_ids,
                "description": "含 scripts/ 的技能编号（须先用 use_skill 加载）",
            },
            "script": {
                "type": "string",
                "description": "scripts/ 下的相对路径，必须在 use_skill 返回的文件清单中",
            },
            "params": {
                "type": "object",
                "description": "传给脚本的参数对象，脚本从 stdin 读取 JSON；按技能说明传值",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "命令行参数（可选），如 [\"word\",\"create\",\"--title\",\"...\"]；不要包含 shell 管道/重定向",
            },
            "input_files": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "执行前写入工作目录的文本文件（路径→内容），如 {\"orders.md\": \"# 标题\\n...\"}；"
                               "用于 md_converter 等需要输入文件的脚本，不能覆盖 SKILL.md 或 scripts/",
            },
        },
        "required": ["skill_id", "script"],
    }


def _run_skill_executor_tool_schema(skills: List[Any]) -> Dict[str, Any]:
    executor_skill_ids = [int(skill.skill_id) for skill in skills if skill.has_executor]
    return {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "integer",
                "enum": executor_skill_ids,
                "description": "含执行器的技能编号（须先用 use_skill 加载）",
            },
            "params": {
                "type": "object",
                "description": "执行器参数，按 use_skill 返回的执行器 parameters schema 传值，不要编造",
            },
        },
        "required": ["skill_id", "params"],
    }


def _create_skill_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "skill_key": {
                "type": "string",
                "description": "技能文件夹名（slug，小写字母/数字开头，仅含小写字母、数字、._-）",
            },
            "content": {
                "type": "string",
                "description": "完整 SKILL.md 内容，必须包含 YAML frontmatter 的 name 和 description，后接 Markdown 指令正文",
            },
            "files": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "附加文本文件（路径→内容），如 references/guide.md；默认不允许写 scripts/",
            },
            "allow_scripts": {
                "type": "boolean",
                "description": "只有用户明确要求可执行脚本时才设为 true；允许写 scripts/ 下的文件",
            },
        },
        "required": ["skill_key", "content"],
    }


def _install_skill_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pack": {
                "type": "string",
                "description": "SkillHub 专家包标识（如 tech-test-automation）；会按 skillhub-pack-install.md 协议安装主技能和全部子技能",
            },
            "skill": {
                "type": "string",
                "description": "SkillHub 单个技能标识（如 @zcwl/multi-search-engine）",
            },
            "url": {
                "type": "string",
                "description": "单个技能 zip 的 HTTPS 直链（与 pack、skill 三选一）",
            },
        },
    }


def _uninstall_skill_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pack": {"type": "string", "description": "SkillHub 专家包标识（如 tech-test-automation）；卸载整个专家包"},
            "skill_id": {"type": "integer", "description": "技能编号（单技能，与 skill_key 二选一）"},
            "skill_key": {"type": "string", "description": "技能文件夹名（单技能，与 skill_id 二选一）"},
        },
    }


def build_agent_tools_schema(
    include_order: bool = True,
    exclude: Optional[set] = None,
    allowed_tools: Optional[set] = None,
    query_paths: Optional[set] = None,
    reasoning_types: Optional[set] = None,
    order_fields: Optional[set] = None,
    skills: Optional[List[Any]] = None,
    script_execution_available: bool = False,
    include_skill_admin: bool = False,
    skill_admin_tools: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """生成 OpenAI function calling 工具清单；exclude 为运行时禁用工具名集合。

    allowed_tools / query_paths / reasoning_types / order_fields 由团队能力解析提供，
    未提供时保持原有全量行为（兼容旧调用）。skills 为团队有效技能索引；
    技能工具不受能力推导的 allowed_tools 过滤，仅受 exclude 控制。
    """
    excluded = exclude or set()
    specs: List[Dict[str, Any]] = []
    if skills:
        specs.append({
            "name": "use_skill",
            "description": "加载团队技能的完整指令（渐进披露）。需求与技能说明匹配时先调用；技能只是方法，不改变能力边界。",
            "parameters": _use_skill_tool_schema(skills),
        })
        specs.append({
            "name": "read_skill_file",
            "description": "读取技能文件夹内的文本资源（优先 references/assets）。不要为了推断用法读取 scripts/ 源码，"
                           "SKILL.md 已给出命令与参数；二进制与超 64KB 文件不可读。须先 use_skill 加载。",
            "parameters": _read_skill_file_tool_schema(skills),
        })
        if script_execution_available and any(skill.has_scripts for skill in skills):
            specs.append({
                "name": "run_skill_script",
                "description": "在隔离沙箱中执行技能 scripts/ 下的脚本。生成文档/表格等任务在查询数据后直接调用；"
                               "script 用 SKILL.md 中的路径（如 scripts/wps.py），args 按 SKILL.md 示例传。"
                               "必须先 use_skill 加载，script 必须在返回的文件清单中。",
                "parameters": _run_skill_script_tool_schema(skills),
            })
        if any(skill.has_executor for skill in skills):
            specs.append({
                "name": "run_skill_executor",
                "description": "执行技能绑定的只读执行器。必须先 use_skill 加载技能，并按返回的 parameters schema 传参。",
                "parameters": _run_skill_executor_tool_schema(skills),
            })
    if include_skill_admin:
        admin_specs = [
            {
                "name": "create_skill",
                "description": "创建一个新技能（写入技能库）。需要完整 SKILL.md；默认只允许指令与资源，"
                               "只有用户明确要求可执行脚本时才传 allow_scripts=true。",
                "parameters": _create_skill_tool_schema(),
            },
            {
                "name": "install_skill",
                "description": "从 SkillHub 专家包（pack）或 HTTPS 公网 zip 直链安装技能包到技能库。",
                "parameters": _install_skill_tool_schema(),
            },
            {
                "name": "uninstall_skill",
                "description": "卸载导入的技能或 SkillHub 专家包（pack，连同子技能）；内置技能不可卸载。",
                "parameters": _uninstall_skill_tool_schema(),
            },
        ]
        specs.extend(
            spec for spec in admin_specs
            if skill_admin_tools is None or spec["name"] in skill_admin_tools
        )
    specs.extend([
        {
            "name": "call_query_agent",
            "description": "调用查询智能体：中台只读查询（订单/物料/齐套/库存/供应商/品质/生产）。path 只能选白名单枚举。"
                           "数据较多时可翻页（params.page/page_size，最大 200），不要重复拉取相同页码。",
            "parameters": _query_tool_schema(),
        },
        {
            "name": "call_reasoning_agent",
            "description": "调用推理智能体：只读大模型分析（交期/齐套/品质/生产，带证据），耗时较长。",
            "parameters": _reasoning_tool_schema(),
        },
        {
            "name": "hub_query",
            "description": "调用 Hub 统一查询：查询其他系统的只读数据（当前支持 PLM 研发项目）。capability 只能选白名单枚举。",
            "parameters": _hub_query_tool_schema(),
        },
    ])
    if include_order:
        specs.append({
            "name": "call_order_agent",
            "description": _order_tool_description(),
            "parameters": _order_tool_schema(order_fields),
        })
    if allowed_tools and "create_feedback" in allowed_tools:
        specs.append({
            "name": "create_feedback",
            "description": "创建问题反馈：代用户提交系统问题/建议/咨询（直接创建，无需确认；可撤销本人待处理的反馈）。",
            "parameters": _feedback_create_tool_schema(),
        })
    if allowed_tools and "revoke_feedback" in allowed_tools:
        specs.append({
            "name": "revoke_feedback",
            "description": "撤销问题反馈：仅能撤销当前用户本人提交且仍待处理的反馈。",
            "parameters": _feedback_revoke_tool_schema(),
        })
    if query_paths is not None:
        for spec in specs:
            if spec["name"] == "call_query_agent":
                spec["parameters"] = _query_tool_schema()
                spec["parameters"]["properties"]["path"]["enum"] = sorted(query_paths)
    if reasoning_types is not None:
        for spec in specs:
            if spec["name"] == "call_reasoning_agent":
                spec["parameters"] = _reasoning_tool_schema()
                spec["parameters"]["properties"]["task_type"]["enum"] = sorted(reasoning_types)
    return [
        {"type": "function", "function": spec}
        for spec in specs
        if spec["name"] not in excluded
        and (
            allowed_tools is None
            or spec["name"] in allowed_tools
            or spec["name"] in SKILL_TOOLS
            or spec["name"] in ADMIN_SKILL_TOOLS
        )
    ]


def normalize_tool_input(tool_name: str, args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把 LLM 工具入参归一化为执行面 agent 的派单入参。"""
    if tool_name in FEEDBACK_TOOLS:
        raise ValueError("问题反馈工具由后端本地执行，不参与执行面派单归一化")
    if tool_name in SKILL_TOOLS or tool_name in ADMIN_SKILL_TOOLS:
        raise ValueError("技能工具由后端本地执行，不参与执行面派单归一化")
    args = args if isinstance(args, dict) else {}
    if tool_name == "call_reasoning_agent":
        return {
            "prompt": args.get("prompt", ""),
            "task_type": args.get("task_type"),
            "context": {"businessObjectRef": args.get("businessObjectRef", "")},
            "constraints": {"read_only": True, "require_evidence": True},
        }
    if tool_name == "call_order_agent":
        return {
            "operation": args.get("operation") or DEFAULT_ASSISTANT_OPERATION,
            "orderNo": args.get("order_no", ""),
            "changes": {"fields": args.get("fields") or {}},
        }
    return {"path": args.get("path"), "params": args.get("params") or {}}


def validate_tool_input(tool_name: str, args: Optional[Dict[str, Any]]) -> Optional[str]:
    """校验 LLM 工具入参；合法返回 None，非法返回原因字符串。"""
    if tool_name in FEEDBACK_TOOLS:
        raise ValueError("问题反馈工具由后端本地执行，不参与派单参数校验")
    if tool_name in SKILL_TOOLS or tool_name in ADMIN_SKILL_TOOLS:
        raise ValueError("技能工具由后端本地执行，不参与派单参数校验")
    capability = CAPABILITY_BY_TOOL[tool_name]
    return validate_task_input(capability, normalize_tool_input(tool_name, args))


def _item_count(result: Any) -> int:
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        return len(result["items"])
    return 1 if result else 0


async def _run_feedback_tool(
    tool_name: str,
    args: Dict[str, Any],
    *,
    db: Any,
    user_context: Any,
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    """执行问题反馈工具（create/revoke）：后端本地落库，不经执行面智能体。"""
    from app.services.basicdata.feedback_service import (
        FeedbackError,
        create_feedback,
        is_admin,
        publish_unread_updates,
        revoke_feedback,
    )

    if db is None or user_context is None:
        return {"ok": False, "online": True, "result": None,
                "error": "问题反馈需要登录上下文", "item_count": 0}
    permissions = getattr(user_context, "permissions", {}) or {}
    if not is_admin({"role": getattr(user_context, "role_code", "")}) \
            and not check_permission(permissions, "topbar.feedback", "read"):
        return {"ok": False, "online": True, "result": None,
                "error": "当前用户没有提交问题反馈的权限", "item_count": 0}

    args = args if isinstance(args, dict) else {}
    user = getattr(user_context, "user", None)
    user_id = int(getattr(user, "id", 0) or 0)
    started_at = now_iso()
    loop_start = time.perf_counter()
    report_assistant_event(
        trace_id, "tool_call", tool_name, "started",
        f"调用{AGENT_TOOL_LABELS[tool_name]}", {"input": args}, started_at=started_at,
        task_id=task_id, step_id=step_id, tool=tool_name,
    )

    def _result(ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
        report_assistant_event(
            trace_id, "tool_result", tool_name, "completed" if ok else "failed",
            (error or "操作成功")[:200], {"feedback": result} if ok else {"input": args},
            started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool=tool_name,
        )
        return {"ok": ok, "online": True, "result": result, "error": error, "item_count": 1 if ok else 0}

    try:
        if tool_name == "create_feedback":
            fb, handler_ids = await create_feedback(
                db,
                submitter_id=user_id,
                submitter_name=(getattr(user, "username", "") or ""),
                title=str(args.get("title") or "").strip(),
                description=str(args.get("description") or "").strip(),
                subtype=args.get("type"),
                severity=args.get("severity"),
            )
            await publish_unread_updates(db, handler_ids)
            return _result(True, {
                "feedback_id": int(fb.id), "title": fb.title,
                "type": fb.type, "severity": fb.severity, "status": fb.status,
            })
        feedback_id = args.get("feedback_id")
        result = await revoke_feedback(db, feedback_id=int(feedback_id), user_id=user_id)
        return _result(True, result)
    except FeedbackError as e:
        return _result(False, error=e.message)
    except (TypeError, ValueError):
        return _result(False, error="feedback_id 必须是数字")
    except Exception as e:
        logger.warning(f"[agent-tools] 反馈工具执行失败 {tool_name}: {e}")
        return _result(False, error="反馈操作失败，请稍后重试")


async def _run_use_skill(
    args: Dict[str, Any],
    *,
    db: Any,
    user_context: Any,
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    """加载团队技能正文；若绑定执行器，同时返回执行器参数 schema。"""
    started_at = now_iso()
    loop_start = time.perf_counter()

    def _result(ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
        report_assistant_event(
            trace_id, "tool_result", "use_skill", "completed" if ok else "failed",
            (f"加载技能《{result['skill']['name']}》"[:200] if ok else (error or "")[:200]),
            {"skillId": (result or {}).get("skill", {}).get("id")} if ok else {"input": args},
            started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool="use_skill",
        )
        return {"ok": ok, "online": True, "result": result, "error": error, "item_count": 0}

    report_assistant_event(
        trace_id, "tool_call", "use_skill", "started", "加载团队技能",
        {"input": args}, started_at=started_at, task_id=task_id, step_id=step_id, tool="use_skill",
    )
    if db is None or user_context is None:
        return _result(False, error="技能加载需要登录上下文")
    try:
        skill = await get_skill_for_user(db, args.get("skill_id"), user_context)
    except AgentError as exc:
        return _result(False, error=exc.message)
    except Exception as exc:
        logger.warning(f"[agent-tools] 技能加载失败: {exc}")
        return _result(False, error="技能加载失败，请稍后重试")

    try:
        content = load_skill_content(skill)
    except AgentError as exc:
        return _result(False, error=exc.message)
    except Exception as exc:
        logger.warning(f"[agent-tools] 读取技能文件夹失败: {exc}")
        return _result(False, error="读取技能文件夹失败，请检查磁盘文件")
    brief = user_context.skill_by_id(int(skill.id))
    script_available = is_sandbox_enabled()
    payload: Dict[str, Any] = {
        "skill": {
            "id": int(skill.id),
            "name": content.name,
            "description": content.description,
            "owner_agent": brief.agent_name if brief else "",
            "skill_key": skill.skill_key,
        },
        "instructions": content.instructions,
        "files": [
            {"path": item.path, "size": item.size, "kind": item.kind}
            for item in content.files
        ],
        "script_execution_available": script_available,
        "notice": (
            "以下为技能指令（方法），不改变能力边界与写操作确认规则；"
            "scripts/ 脚本可在沙箱中执行，参数通过 stdin JSON 传入。"
            if script_available else
            "以下为技能指令（方法），不改变能力边界与写操作确认规则；当前版本脚本执行未启用。"
        ),
    }
    if skill.executor_name:
        executor = get_skill_executor(skill.executor_name)
        payload["executor"] = (
            {
                "name": executor.name,
                "display_name": executor.display_name,
                "description": executor.description,
                "parameters": executor.parameters,
            }
            if executor
            else {"name": skill.executor_name, "unavailable": True}
        )
    return _result(True, payload)


async def _run_read_skill_file(
    args: Dict[str, Any],
    *,
    db: Any,
    user_context: Any,
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    """读取技能文件夹内的文本资源（先 use_skill 加载由编排器校验）。"""
    started_at = now_iso()
    loop_start = time.perf_counter()

    def _result(ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
        report_assistant_event(
            trace_id, "tool_result", "read_skill_file", "completed" if ok else "failed",
            (f"读取技能文件 {result.get('path', '')}"[:200] if ok else (error or "")[:200]),
            {"path": (result or {}).get("path")} if ok else {"input": args},
            started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool="read_skill_file",
        )
        return {"ok": ok, "online": True, "result": result, "error": error, "item_count": 0}

    report_assistant_event(
        trace_id, "tool_call", "read_skill_file", "started", "读取技能资源",
        {"input": args}, started_at=started_at, task_id=task_id, step_id=step_id,
        tool="read_skill_file",
    )
    if db is None or user_context is None:
        return _result(False, error="技能文件读取需要登录上下文")
    try:
        skill = await get_skill_for_user(db, args.get("skill_id"), user_context)
        result = read_skill_text_file(
            skill, str(args.get("path") or ""),
            max_bytes=RUNTIME_SKILL_FILE_MAX_BYTES,
        )
    except AgentError as exc:
        return _result(False, error=exc.message)
    except Exception as exc:
        logger.warning(f"[agent-tools] 技能文件读取失败: {exc}")
        return _result(False, error="技能文件读取失败")
    return _result(True, result=result)


_BLOCKED_ARTIFACT_SUFFIXES = {
    ".exe", ".bat", ".cmd", ".ps1", ".sh", ".py", ".js", ".jar",
    ".dll", ".so", ".msi", ".com", ".scr", ".vbs",
}
_ARTIFACT_MIME_FALLBACK = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".html": "text/html",
    ".json": "application/json",
    ".txt": "text/plain",
}
_MAX_ARTIFACT_BYTES = 20 * 1024 * 1024


def _save_skill_artifacts(payload: Dict[str, Any]) -> tuple:
    encoded = payload.get("artifacts")
    if not isinstance(encoded, str) or not encoded:
        return [], None
    try:
        data = base64.b64decode(encoded)
    except (ValueError, TypeError):
        return [], "技能产物解码失败"
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return [], "技能产物格式非法"
    storage = get_storage()
    files = []
    total = 0
    try:
        for info in archive.infolist()[:20]:
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if not name or Path(name).suffix.lower() in _BLOCKED_ARTIFACT_SUFFIXES:
                continue
            content = archive.read(info)
            total += len(content)
            if total > _MAX_ARTIFACT_BYTES:
                break
            mime = (
                mimetypes.guess_type(name)[0]
                or _ARTIFACT_MIME_FALLBACK.get(Path(name).suffix.lower())
                or "application/octet-stream"
            )
            stored = storage.save(content, name, mime, "skill_output")
            files.append({
                "name": stored.name,
                "path": info.filename,
                "size": stored.size,
                "mime": stored.mime,
                "url": stored.url,
            })
    except Exception as exc:
        logger.warning(f"[agent-tools] 技能产物保存失败: {exc}")
        return files, "技能产物保存失败"
    return files, None


async def _run_skill_script(
    args: Dict[str, Any],
    *,
    db: Any,
    user_context: Any,
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    """在独立 sandbox 中执行技能 scripts/ 下的脚本。"""
    started_at = now_iso()
    loop_start = time.perf_counter()

    def _result(ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
        report_assistant_event(
            trace_id, "tool_result", "run_skill_script", "completed" if ok else "failed",
            ("技能脚本执行完成" if ok else (error or "")[:200]),
            {"result": result} if ok else {"input": args},
            started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool="run_skill_script",
        )
        return {
            "ok": ok, "online": True, "result": result, "error": error,
            "item_count": _item_count(result) if ok else 0,
        }

    report_assistant_event(
        trace_id, "tool_call", "run_skill_script", "started", "执行技能脚本",
        {"input": args}, started_at=started_at, task_id=task_id, step_id=step_id,
        tool="run_skill_script",
    )
    if db is None or user_context is None:
        return _result(False, error="技能脚本执行需要登录上下文")
    try:
        skill = await get_skill_for_user(db, args.get("skill_id"), user_context)
        content = load_skill_content(skill)
    except AgentError as exc:
        return _result(False, error=exc.message)
    script = str(args.get("script") or "").strip().replace("\\", "/")
    matched = next(
        (item for item in content.files if item.path == script and item.kind == "script"),
        None,
    )
    if matched is None:
        return _result(False, error="脚本不在技能 scripts/ 清单内")
    params = args.get("params") or {}
    if not isinstance(params, dict):
        return _result(False, error="params 必须是对象")
    raw_args = args.get("args") or []
    if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
        return _result(False, error="args 必须是字符串数组")
    if len(raw_args) > 32 or any(len(item) > 2000 or "\x00" in item for item in raw_args):
        return _result(False, error="args 参数过多或过长")
    raw_inputs = args.get("input_files") or {}
    if not isinstance(raw_inputs, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_inputs.items()
    ):
        return _result(False, error="input_files 必须是 路径→文本 的对象")

    try:
        payload = await run_sandbox_script(skill, script, params, raw_args, raw_inputs)
    except AgentError as exc:
        return _result(False, error=exc.message)
    except Exception as exc:
        logger.warning(f"[agent-tools] 技能沙箱调用失败: {exc}")
        return _result(False, error="技能沙箱调用失败，请稍后重试")

    max_output = int(get_settings().SKILL_SCRIPT_MAX_OUTPUT_BYTES or 8000)

    def _clip(value: Any) -> str:
        return str(value or "")[:max_output]

    files, artifact_error = _save_skill_artifacts(payload)
    result = {
        "exit_code": payload.get("exit_code"),
        "stdout": _clip(payload.get("stdout")),
        "stderr": _clip(payload.get("stderr")),
        "duration_ms": payload.get("duration_ms"),
        "truncated": bool(payload.get("truncated")),
        "files": files,
    }
    if artifact_error:
        result["artifact_error"] = artifact_error
    if payload.get("artifacts_truncated"):
        result["artifacts_truncated"] = True
    if not payload.get("ok"):
        error = (result["stderr"] or result["stdout"] or "脚本执行失败")[:500]
        return _result(False, result=result, error=error)
    return _result(True, result=result)


async def _run_skill_executor_tool(
    args: Dict[str, Any],
    *,
    db: Any,
    user_context: Any,
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    """执行技能绑定的已注册只读执行器。"""
    started_at = now_iso()
    loop_start = time.perf_counter()

    def _result(ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
        report_assistant_event(
            trace_id, "tool_result", "run_skill_executor", "completed" if ok else "failed",
            "技能执行完成" if ok else (error or "")[:200],
            {"result": result} if ok else {"input": args},
            started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool="run_skill_executor",
        )
        return {
            "ok": ok, "online": True, "result": result, "error": error,
            "item_count": _item_count(result) if ok else 0,
        }

    report_assistant_event(
        trace_id, "tool_call", "run_skill_executor", "started", "执行技能执行器",
        {"input": args}, started_at=started_at, task_id=task_id, step_id=step_id,
        tool="run_skill_executor",
    )
    if db is None or user_context is None:
        return _result(False, error="技能执行需要登录上下文")
    try:
        skill = await get_skill_for_user(db, args.get("skill_id"), user_context)
    except AgentError as exc:
        return _result(False, error=exc.message)
    if not skill.executor_name:
        return _result(False, error="该技能未绑定可执行器")
    executor = get_skill_executor(skill.executor_name)
    if executor is None:
        return _result(False, error=f"执行器不可用：{skill.executor_name}")
    brief = user_context.skill_by_id(int(skill.id))
    member = user_context.member_by_id(brief.agent_id) if brief else None
    invalid = validate_executor_for_member(executor, member)
    if invalid:
        return _result(False, error=invalid)
    params = args.get("params") or {}
    if not isinstance(params, dict):
        return _result(False, error="params 必须是对象")

    outcome = await run_registered_executor(
        executor,
        params,
        SkillExecutorContext(
            db=db,
            user_context=user_context,
            trace_id=trace_id,
            task_id=task_id or "",
            step_id=step_id or 0,
            session_id=trace_id,
        ),
    )
    if not outcome.get("ok"):
        return _result(False, error=outcome.get("error") or "执行器执行失败")
    return _result(True, result=outcome.get("result"))


def _require_skill_manage(user_context: Any, tool_name: str) -> None:
    if user_context is None:
        raise AgentError("技能管理需要登录上下文")
    allowed = allowed_skill_admin_tools(
        getattr(user_context, "permissions", {}) or {},
        getattr(user_context, "effective_capabilities", set()) or set(),
    )
    if tool_name not in allowed:
        raise AgentError(
            "当前团队没有该技能管理能力（需要 ai.skill.manage/ai.agent.admin 权限，"
            "或团队成员具备对应技能管理能力）"
        )


async def _audit_skill_action(
    db: Any, user_context: Any, skill_id: int, action: str, skill_key: str
) -> None:
    if db is None:
        return
    operator = getattr(getattr(user_context, "user", None), "username", "") or ""
    try:
        await log_audit(
            db, "agent_skill", int(skill_id), action, field_name="skill_key",
            new_value=(skill_key or "")[:500], operator=operator,
        )
    except Exception as exc:
        logger.warning(f"[agent-tools] 技能审计失败: {exc}")


async def _run_create_skill(
    args: Dict[str, Any],
    *,
    db: Any,
    user_context: Any,
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    started_at = now_iso()
    loop_start = time.perf_counter()

    def _result(ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
        report_assistant_event(
            trace_id, "tool_result", "create_skill", "completed" if ok else "failed",
            (f"创建技能 {result.get('skill_key', '')}"[:200] if ok else (error or "")[:200]),
            {"result": result} if ok else {"input": args},
            started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool="create_skill",
        )
        return {"ok": ok, "online": True, "result": result, "error": error, "item_count": 1 if ok else 0}

    report_assistant_event(
        trace_id, "tool_call", "create_skill", "started", "创建技能",
        {"input": args}, started_at=started_at, task_id=task_id, step_id=step_id, tool="create_skill",
    )
    try:
        _require_skill_manage(user_context, "create_skill")
        if db is None:
            raise AgentError("技能管理需要数据库上下文")
        files = args.get("files") or {}
        if not isinstance(files, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in files.items()
        ):
            raise AgentError("files 必须是 路径→文本 的对象")
        row = await create_skill_from_content(
            db,
            content=str(args.get("content") or ""),
            skill_key=str(args.get("skill_key") or ""),
            files=files,
            allow_scripts=bool(args.get("allow_scripts")),
            created_by_user_id=int(user_context.user.id),
        )
        await _audit_skill_action(db, user_context, int(row.id), "create", row.skill_key or "")
        return _result(True, {
            "skill_id": int(row.id),
            "skill_key": row.skill_key,
            "name": row.name,
            "message": "已创建；请绑定到智能体后使用",
        })
    except AgentError as exc:
        return _result(False, error=exc.message)
    except Exception as exc:
        logger.exception(f"[agent-tools] 创建技能失败: {exc}")
        return _result(False, error="创建技能失败")


async def _run_install_skill(
    args: Dict[str, Any],
    *,
    db: Any,
    user_context: Any,
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    started_at = now_iso()
    loop_start = time.perf_counter()

    def _result(ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
        report_assistant_event(
            trace_id, "tool_result", "install_skill", "completed" if ok else "failed",
            (f"安装技能 {result.get('skill_key', '')}"[:200] if ok else (error or "")[:200]),
            {"result": result} if ok else {"input": args},
            started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool="install_skill",
        )
        return {"ok": ok, "online": True, "result": result, "error": error, "item_count": 1 if ok else 0}

    report_assistant_event(
        trace_id, "tool_call", "install_skill", "started", "安装技能",
        {"input": args}, started_at=started_at, task_id=task_id, step_id=step_id, tool="install_skill",
    )
    try:
        _require_skill_manage(user_context, "install_skill")
        if db is None:
            raise AgentError("技能管理需要数据库上下文")
        pack = str(args.get("pack") or "").strip()
        skill = str(args.get("skill") or args.get("skill_key") or "").strip()
        url = str(args.get("url") or "").strip()
        if pack:
            summary = await install_skillhub_pack(
                db, pack, created_by_user_id=int(user_context.user.id),
            )
            for item in summary.get("installed") or []:
                await _audit_skill_action(
                    db, user_context, int(item["skill_id"]), "install", item.get("skill_key") or "",
                )
            summary["message"] = "专家包已安装；请绑定需要的技能到智能体"
            return _result(True, summary)
        if skill:
            result = await install_skillhub_skill(
                db, skill, created_by_user_id=int(user_context.user.id),
            )
            row = await resolve_skill_for_manage(db, skill_id=int(result["id"]))
            await _audit_skill_action(
                db, user_context, int(row.id), "install", row.skill_key or "",
            )
            return _result(True, {
                "skill_id": int(row.id),
                "skill_key": row.skill_key,
                "name": row.name,
                "message": "已安装；请绑定到智能体后使用",
            })
        if not url:
            raise AgentError("需要提供 SkillHub 技能标识、专家包 pack 或技能 zip 的 url")
        result = await install_skill_from_url(
            db, url, created_by_user_id=int(user_context.user.id),
        )
        row = await resolve_skill_for_manage(db, skill_id=int(result["id"]))
        await _audit_skill_action(db, user_context, int(row.id), "install", row.skill_key or "")
        return _result(True, {
            "skill_id": int(row.id),
            "skill_key": row.skill_key,
            "name": row.name,
            "message": "已安装；请绑定到智能体后使用",
        })
    except AgentError as exc:
        return _result(False, error=exc.message)
    except Exception as exc:
        logger.exception(f"[agent-tools] 安装技能失败: {exc}")
        return _result(False, error="安装技能失败")


async def _run_uninstall_skill(
    args: Dict[str, Any],
    *,
    db: Any,
    user_context: Any,
    trace_id: str = "",
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    started_at = now_iso()
    loop_start = time.perf_counter()

    def _result(ok: bool, result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
        report_assistant_event(
            trace_id, "tool_result", "uninstall_skill", "completed" if ok else "failed",
            (f"卸载技能 {result.get('skill_key', '')}"[:200] if ok else (error or "")[:200]),
            {"result": result} if ok else {"input": args},
            started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
            task_id=task_id, step_id=step_id, tool="uninstall_skill",
        )
        return {"ok": ok, "online": True, "result": result, "error": error, "item_count": 1 if ok else 0}

    report_assistant_event(
        trace_id, "tool_call", "uninstall_skill", "started", "卸载技能",
        {"input": args}, started_at=started_at, task_id=task_id, step_id=step_id,
        tool="uninstall_skill",
    )
    try:
        _require_skill_manage(user_context, "uninstall_skill")
        if db is None:
            raise AgentError("技能管理需要数据库上下文")
        pack = str(args.get("pack") or "").strip()
        if pack:
            result = await uninstall_skillhub_pack(db, pack)
        else:
            raw_id = args.get("skill_id")
            skill_id = int(raw_id) if raw_id not in (None, "") else None
            skill_key = str(args.get("skill_key") or "")
            try:
                row = await resolve_skill_for_manage(
                    db, skill_id=skill_id, skill_key=skill_key,
                )
            except AgentError as exc:
                if "技能不存在" in exc.message and skill_key:
                    result = await uninstall_skillhub_pack(db, skill_key)
                else:
                    raise
            else:
                result = await uninstall_skill_with_pack(db, int(row.id))
        for item in result.get("removed") or []:
            await _audit_skill_action(
                db, user_context, int(item["id"]), "delete", item.get("skill_key") or "",
            )
        return _result(True, {
            "removed": result.get("removed") or [],
            "skipped": result.get("skipped") or [],
            "errors": result.get("errors") or [],
            "is_pack": bool(result.get("is_pack")),
            "message": "专家包已卸载" if result.get("is_pack") else "已卸载",
        })
    except (TypeError, ValueError):
        return _result(False, error="skill_id 必须是数字")
    except AgentError as exc:
        return _result(False, error=exc.message)
    except Exception as exc:
        logger.exception(f"[agent-tools] 卸载技能失败: {exc}")
        return _result(False, error="卸载技能失败")


async def execute_agent_tool(
    tool_name: str,
    args: Dict[str, Any],
    *,
    operator_user_id: str = "",
    trace_id: str = "",
    hub_trace_id: str = "",
    caller: Optional[Dict[str, Any]] = None,
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
    actor_token: str = "",
    db: Any = None,
    user_context: Any = None,
) -> Dict[str, Any]:
    """执行智能体工具（query / reasoning / hub_query / feedback / 技能）。

    trace_id 为会话观测 trace；hub_trace_id 为每请求 Hub caller/借调 trace。
    返回：{"ok", "online", "result", "error", "item_count"}
    - 参数非法 / agent 离线 / 繁忙 / 执行失败均返回 ok=False + error，绝不抛错。
    """
    if tool_name == "use_skill":
        return await _run_use_skill(
            args, db=db, user_context=user_context,
            trace_id=trace_id, task_id=task_id, step_id=step_id,
        )
    if tool_name == "read_skill_file":
        return await _run_read_skill_file(
            args, db=db, user_context=user_context,
            trace_id=trace_id, task_id=task_id, step_id=step_id,
        )
    if tool_name == "run_skill_script":
        return await _run_skill_script(
            args, db=db, user_context=user_context,
            trace_id=trace_id, task_id=task_id, step_id=step_id,
        )
    if tool_name == "run_skill_executor":
        return await _run_skill_executor_tool(
            args, db=db, user_context=user_context,
            trace_id=trace_id, task_id=task_id, step_id=step_id,
        )
    if tool_name == "create_skill":
        return await _run_create_skill(
            args, db=db, user_context=user_context,
            trace_id=trace_id, task_id=task_id, step_id=step_id,
        )
    if tool_name == "install_skill":
        return await _run_install_skill(
            args, db=db, user_context=user_context,
            trace_id=trace_id, task_id=task_id, step_id=step_id,
        )
    if tool_name == "uninstall_skill":
        return await _run_uninstall_skill(
            args, db=db, user_context=user_context,
            trace_id=trace_id, task_id=task_id, step_id=step_id,
        )
    if tool_name == "hub_query":
        return await _run_hub_query(
            args, operator_user_id=operator_user_id, trace_id=trace_id,
            hub_trace_id=hub_trace_id, caller=caller,
            task_id=task_id, step_id=step_id,
        )
    if tool_name in FEEDBACK_TOOLS:
        return await _run_feedback_tool(
            tool_name, args, db=db, user_context=user_context,
            trace_id=trace_id, task_id=task_id, step_id=step_id,
        )
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
        actor_token=actor_token,
        trace_id=hub_trace_id,
        caller=caller,
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


async def _run_hub_query(
    args: Dict[str, Any],
    *,
    operator_user_id: str = "",
    trace_id: str = "",
    hub_trace_id: str = "",
    caller: Optional[Dict[str, Any]] = None,
    task_id: Optional[str] = None,
    step_id: Optional[int] = None,
) -> Dict[str, Any]:
    """执行 hub_query：校验能力 → 发起 Hub 调用 → 轮询至终态（30s 收口）。

    返回 {"ok", "online", "result", "error", "item_count"}；online=False 表示 Hub 未配置。
    """
    capability = (args or {}).get("capability") or ""
    params = (args or {}).get("params") or {}
    started_at = now_iso()
    loop_start = time.perf_counter()
    if not capability:
        report_assistant_event(
            trace_id, "tool_result", "hub_query", "failed", "参数非法：缺少 capability",
            {"params": args}, started_at=started_at,
            task_id=task_id, step_id=step_id, tool="hub_query",
        )
        return {"ok": False, "online": True, "result": None,
                "error": "参数非法：缺少 capability", "item_count": 0}
    report_assistant_event(
        trace_id, "tool_call", "hub_query", "started",
        f"调用 Hub 查询 {capability}", {"input": {"capability": capability, "params": params}},
        started_at=started_at, task_id=task_id, step_id=step_id, tool="hub_query",
    )

    if not is_hub_enabled():
        outcome = {"ok": False, "online": False, "result": None,
                   "error": "Hub 未配置，跨系统查询暂不可用", "item_count": 0}
    else:
        invalid = await validate_capability(capability)
        if invalid:
            outcome = {"ok": False, "online": True, "result": None,
                       "error": f"参数非法：{invalid}", "item_count": 0}
        else:
            to_system = provider_system(capability) or ""
            if not to_system:
                outcome = {"ok": False, "online": True, "result": None,
                           "error": "Hub 能力目录缺少 providerSystem", "item_count": 0}
            else:
                polled = await query_and_poll(
                    capability, params, to_system=to_system,
                    caller=caller, trace_id=hub_trace_id,
                )
                outcome = {
                    "ok": bool(polled.get("ok")),
                    "online": True,
                    "result": polled.get("result"),
                    "error": polled.get("error"),
                    "item_count": _item_count(polled.get("result")),
                }

    duration_ms = round((time.perf_counter() - loop_start) * 1000, 2)
    report_assistant_event(
        trace_id, "tool_result", "hub_query",
        "completed" if outcome.get("ok") else "failed",
        f"返回 {outcome['item_count']} 条" if outcome.get("ok") else (outcome.get("error") or "")[:200],
        {"itemCount": outcome["item_count"]} if outcome.get("ok")
        else {"input": {"capability": capability, "params": params}},
        started_at=started_at, ended_at=now_iso(), duration_ms=duration_ms,
        task_id=task_id, step_id=step_id, tool="hub_query",
    )
    return outcome


async def query_order_current_fields(
    order_no: str, *, operator_user_id: str = "", trace_id: str = "",
    task_id: Optional[str] = None, step_id: Optional[int] = None,
    actor_token: str = "",
) -> Dict[str, Any]:
    """写确认前经查询智能体读取订单当前值（4 个可写字段）。

    返回 {"values": {field: value|None}, "missing": bool, "row": dict|None, "error": str|None}
    - missing=True 表示未能读到旧值（agent 离线 / 订单不存在 / 接口未返回字段）；
    - row 为精确匹配到的完整订单行（写后完整性校验用，不额外发起查询）。
    """
    outcome = await execute_agent_tool(
        "call_query_agent",
        {"path": "/external/orders/list", "params": {"keyword": order_no, "page_size": 100}},
        operator_user_id=operator_user_id,
        trace_id=trace_id,
        task_id=task_id,
        step_id=step_id,
        actor_token=actor_token,
    )
    if not outcome.get("ok"):
        return {"values": {f: None for f in ORDER_READBACK_FIELDS}, "missing": True,
                "row": None, "error": outcome.get("error")}
    items = (outcome.get("result") or {}).get("items") or []
    matched = next((it for it in items if str(it.get("order_no") or "") == order_no), None)
    if not matched:
        return {"values": {f: None for f in ORDER_READBACK_FIELDS}, "missing": True,
                "row": None, "error": f"未查到订单 {order_no}"}
    values = {f: matched.get(f) for f in ORDER_READBACK_FIELDS}
    missing = any(f not in matched for f in ORDER_READBACK_FIELDS)
    return {"values": values, "missing": missing, "row": matched, "error": None}


async def _noop_execute(db=None, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """注册表占位执行体：编排器不经过注册表执行智能体工具，只经 build_agent_tools_schema 下发。"""
    return {"error": "执行面智能体工具由编排器统一执行，不经过注册表直接调用"}


def _use_skill_registry_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "skill_id": {"type": "integer", "description": "团队技能编号"},
        },
        "required": ["skill_id"],
    }


def _read_skill_file_registry_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "skill_id": {"type": "integer", "description": "技能编号"},
            "path": {"type": "string", "description": "技能文件相对路径"},
        },
        "required": ["skill_id", "path"],
    }


def _run_skill_script_registry_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "skill_id": {"type": "integer", "description": "技能编号"},
            "script": {"type": "string", "description": "scripts/ 下的脚本路径"},
            "params": {"type": "object", "description": "脚本参数"},
            "args": {"type": "array", "items": {"type": "string"}, "description": "命令行参数"},
            "input_files": {"type": "object", "description": "执行前写入的文本文件"},
        },
        "required": ["skill_id", "script"],
    }


def _run_skill_executor_registry_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "skill_id": {"type": "integer", "description": "含执行器的技能编号"},
            "params": {"type": "object", "description": "执行器参数"},
        },
        "required": ["skill_id", "params"],
    }


def register_agent_tools() -> None:
    """把智能体工具与技能工具注册进全局注册表（/tools、禁用校验、{{TOOLS}} 占位符用）。"""
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
        f"调用订单智能体：{_order_tool_titles()}（执行前需用户确认）",
        _order_tool_schema(),
        display_name="订单智能体",
        keywords=["修改", "写入", "合同交期", "承诺交期", "交期", "出货计划"],
        category="agent",
        read_only=False,
        requires_confirmation=True,
    )(_noop_execute)
    register_tool(
        "hub_query",
        "调用 Hub 统一查询：查询其他系统的只读数据（当前支持 PLM 研发项目）",
        _hub_query_tool_schema(),
        display_name="Hub 外部查询",
        keywords=["跨系统", "PLM", "研发项目", "外部查询"],
        category="agent",
        read_only=True,
    )(_noop_execute)
    register_tool(
        "create_feedback",
        "创建问题反馈：代用户提交系统问题/建议/咨询（直接创建，可撤销本人待处理的反馈）",
        _feedback_create_tool_schema(),
        display_name="创建问题反馈",
        keywords=["反馈", "提反馈", "建议", "问题反馈", "咨询"],
        category="agent",
        read_only=False,
    )(_noop_execute)
    register_tool(
        "revoke_feedback",
        "撤销问题反馈：仅能撤销当前用户本人提交且仍待处理的反馈",
        _feedback_revoke_tool_schema(),
        display_name="撤销问题反馈",
        keywords=["撤销反馈", "撤回反馈", "删除反馈"],
        category="agent",
        read_only=False,
    )(_noop_execute)
    register_tool(
        "use_skill",
        "加载团队技能的完整指令（按需加载，技能不改变能力边界）",
        _use_skill_registry_schema(),
        display_name="团队技能",
        keywords=["技能", "skill", "方法", "步骤"],
        category="skill",
        read_only=True,
    )(_noop_execute)
    register_tool(
        "read_skill_file",
        "读取技能文件夹内的文本资源（须先加载技能）",
        _read_skill_file_registry_schema(),
        display_name="技能资源",
        keywords=["技能", "资源", "文件", "参考"],
        category="skill",
        read_only=True,
    )(_noop_execute)
    register_tool(
        "run_skill_script",
        "在隔离沙箱中执行技能 scripts/ 下的脚本（须先加载技能）",
        _run_skill_script_registry_schema(),
        display_name="技能脚本",
        keywords=["技能", "脚本", "沙箱", "执行"],
        category="skill",
        read_only=True,
    )(_noop_execute)
    register_tool(
        "run_skill_executor",
        "执行技能绑定的只读执行器（须先加载技能）",
        _run_skill_executor_registry_schema(),
        display_name="技能执行器",
        keywords=["技能", "执行器", "执行"],
        category="skill",
        read_only=True,
    )(_noop_execute)
    register_tool(
        "create_skill",
        "创建技能（写入技能库；默认只写指令与资源）",
        _create_skill_tool_schema(),
        display_name="创建技能",
        keywords=["创建技能", "新建技能", "skill"],
        category="skill-admin",
        read_only=False,
    )(_noop_execute)
    register_tool(
        "install_skill",
        "从 HTTPS 公网 zip 安装技能",
        _install_skill_tool_schema(),
        display_name="安装技能",
        keywords=["安装技能", "导入技能", "skill"],
        category="skill-admin",
        read_only=False,
    )(_noop_execute)
    register_tool(
        "uninstall_skill",
        "卸载导入的技能（内置技能不可卸载）",
        _uninstall_skill_tool_schema(),
        display_name="卸载技能",
        keywords=["卸载技能", "删除技能", "skill"],
        category="skill-admin",
        read_only=False,
    )(_noop_execute)


register_agent_tools()
