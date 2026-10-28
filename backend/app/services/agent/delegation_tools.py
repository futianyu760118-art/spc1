"""父子智能体委派工具：能力目录、目标校验与执行。"""

from typing import Any, Dict, List

from app.services.agent.capabilities import CONFIGURABLE_CAPABILITIES
from app.services.agent.context import AgentContext
from app.services.agent.delegation import delegate_task


DELEGATION_TOOL_NAMES = frozenset({"list_my_subordinates", "delegate_task"})


def is_delegation_tool(name: str) -> bool:
    return name in DELEGATION_TOOL_NAMES


def _capability_items(codes: List[str]) -> List[dict]:
    return [
        {
            "code": code,
            "name": CONFIGURABLE_CAPABILITIES[code].name,
            "read_only": CONFIGURABLE_CAPABILITIES[code].read_only,
        }
        for code in codes
        if code in CONFIGURABLE_CAPABILITIES
    ]


def build_delegation_tools_schema(
    ctx: AgentContext,
    *,
    delegation_depth: int = 0,
    max_delegation_depth: int = 3,
) -> List[dict]:
    specs: List[dict] = []
    if ctx.can_manage_team:
        specs.append({
            "type": "function",
            "function": {
                "name": "list_my_subordinates",
                "description": "列出我的直属子智能体及其已授权的只读能力。派活前先调用它确认目标。",
                "parameters": {"type": "object", "properties": {}},
            },
        })
    if ctx.is_supervisor and delegation_depth < max_delegation_depth:
        specs.append({
            "type": "function",
            "function": {
                "name": "delegate_task",
                "description": (
                    "把一个只读子任务委派给直属子智能体。目标必须由 list_my_subordinates 确认，"
                    "且具备 capability 对应的能力。子智能体会用它自己的数据范围执行并返回结论。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_user_id": {
                            "type": "integer",
                            "description": "目标直属子智能体绑定的用户 ID",
                        },
                        "capability": {
                            "type": "string",
                            "description": "需要子智能体使用的能力码，如 query.orders / reason.materials",
                        },
                        "instruction": {
                            "type": "string",
                            "description": "要子智能体完成的具体任务、输出要求与约束",
                        },
                        "context": {
                            "type": "object",
                            "description": "可选上下文（业务对象、已知事实、父级结论）",
                        },
                    },
                    "required": ["target_user_id", "capability", "instruction"],
                },
            },
        })
    return specs


def step_summary(name: str, args: Dict[str, Any]) -> str:
    if name == "list_my_subordinates":
        return "查看直属子智能体"
    return f"委派给子智能体（{args.get('capability') or '未知能力'}）"


def validate_delegation_input(name: str, args: Dict[str, Any]) -> str:
    if name == "list_my_subordinates":
        return ""
    if not isinstance(args.get("target_user_id"), int):
        return "缺少 target_user_id；请先调用 list_my_subordinates 选择直属子智能体"
    capability = args.get("capability")
    if not isinstance(capability, str) or not capability.strip():
        return "缺少 capability"
    instruction = args.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        return "缺少 instruction"
    if len(instruction) > 4000:
        return "instruction 不能超过 4000 字"
    return ""


async def execute_delegation_tool(
    db,
    ctx: AgentContext,
    name: str,
    args: Dict[str, Any],
    *,
    delegation_depth: int,
    max_delegation_depth: int,
    trace_id: str,
) -> Dict[str, Any]:
    if name == "list_my_subordinates":
        return {
            "ok": True,
            "items": [
                {
                    "agent_id": child.agent_id,
                    "user_id": child.user_id,
                    "name": child.display_name,
                    "username": child.username,
                    "status": child.status,
                    "capabilities": _capability_items(child.capabilities),
                }
                for child in ctx.children
            ],
        }
    return await delegate_task(
        db,
        parent_ctx=ctx,
        target_user_id=int(args["target_user_id"]),
        capability=args["capability"].strip(),
        instruction=args["instruction"].strip(),
        context=args.get("context") if isinstance(args.get("context"), dict) else {},
        trace_id=trace_id,
        delegation_depth=delegation_depth,
        max_delegation_depth=max_delegation_depth,
    )
