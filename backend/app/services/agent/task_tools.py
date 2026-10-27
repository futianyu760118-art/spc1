"""助手任务工具：读写工具 schema、确认卡预览与确认执行。"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent.agent import Agent
from app.models.basicdata.user import SysUser
from app.services.agent import hierarchy, policy, task_service
from app.services.agent.context import AgentContext, load_agent_context

logger = logging.getLogger(__name__)

TASK_TOOL_NAMES = {
    "list_my_tasks", "get_task_detail", "start_task", "block_task", "analyze_task",
    "submit_task_report", "list_my_subordinates", "add_subordinate",
    "assign_task", "list_team_tasks", "team_task_summary", "update_task", "remind_task",
    "reassign_task", "cancel_task", "return_task", "update_subordinate_agent",
}

CONFIRM_ACTION_TYPES = {
    "assign_task", "update_task", "reassign_task", "cancel_task", "return_task",
    "add_subordinate", "update_subordinate_agent", "submit_task_report",
}


def _schema(properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def _task_id_prop() -> Dict[str, Any]:
    return {"type": "integer", "description": "任务 ID（列表/详情中返回的 id）"}


def _task_tool_specs() -> Dict[str, Dict[str, Any]]:
    return {
        "list_my_tasks": {
            "description": "查看分配给我的任务（可按状态/关键字过滤，最多返回 20 条）。",
            "parameters": _schema({
                "status": {"type": "string", "description": "状态，逗号分隔：pending/in_progress/blocked/completed/cancelled"},
                "keyword": {"type": "string", "description": "标题/任务号/业务单号关键字"},
            }, []),
        },
        "get_task_detail": {
            "description": "查看任务详情：要求、自动分析、汇报历史、事件流。",
            "parameters": _schema({"task_id": _task_id_prop()}, ["task_id"]),
        },
        "start_task": {
            "description": "开始处理我的任务（pending → in_progress）。",
            "parameters": _schema({"task_id": _task_id_prop()}, ["task_id"]),
        },
        "block_task": {
            "description": "把我的任务标记为阻塞，必须填写原因。",
            "parameters": _schema({
                "task_id": _task_id_prop(),
                "reason": {"type": "string", "description": "阻塞原因"},
            }, ["task_id", "reason"]),
        },
        "analyze_task": {
            "description": "对我的业务任务重新做一次只读自动分析（每小时最多 3 次）。",
            "parameters": _schema({"task_id": _task_id_prop()}, ["task_id"]),
        },
        "submit_task_report": {
            "description": "提交任务汇报（会完成该任务，需用户确认）。",
            "parameters": _schema({
                "task_id": _task_id_prop(),
                "summary": {"type": "string", "description": "汇报摘要（必填）"},
                "result_data": {"type": "object", "description": "结构化结果（可选）"},
                "evidence": {"type": "array", "description": "证据列表（可选）", "items": {"type": "object"}},
            }, ["task_id", "summary"]),
        },
        "list_my_subordinates": {
            "description": "列出我的直属子智能体（姓名、用户名、状态、智能体 ID）。",
            "parameters": _schema({}, []),
        },
        "add_subordinate": {
            "description": "把内部用户添加为直属子智能体（只能绑定无上级且无子智能体的叶子，需用户确认）。",
            "parameters": _schema({
                "user_id": {"type": "integer", "description": "目标用户 ID（与 username 二选一）"},
                "username": {"type": "string", "description": "目标用户登录名（与 user_id 二选一）"},
            }, []),
        },
        "assign_task": {
            "description": "给直属子智能体派发任务（需用户确认）。业务任务需指定 biz_type 和业务对象编号。",
            "parameters": _schema({
                "assignee_user_id": {"type": "integer", "description": "接收人用户 ID（推荐，先调用 list_my_subordinates）"},
                "assignee_name": {"type": "string", "description": "接收人姓名/用户名（无法确定 ID 时使用）"},
                "title": {"type": "string", "description": "任务标题（必填）"},
                "description": {"type": "string", "description": "任务要求"},
                "due_at": {"type": "string", "description": "截止时间 ISO 8601（必填，如 2026-10-30T18:00:00）"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "task_type": {"type": "string", "enum": ["business", "general"]},
                "biz_type": {"type": "string", "enum": ["order", "material_shortage", "quality_issue"]},
                "biz_identifier": {"type": "string", "description": "订单号 / 缺料物料编码或 id / 品质异常编号"},
                "biz_context": {"type": "object", "description": "业务对象附加上下文（缺料任务可带 order_no）"},
            }, ["title", "due_at"]),
        },
        "list_team_tasks": {
            "description": "查看我派发的团队任务（可按接收人/状态/关键字过滤）。",
            "parameters": _schema({
                "status": {"type": "string", "description": "状态，逗号分隔"},
                "assignee_user_id": {"type": "integer", "description": "按接收人筛选"},
                "keyword": {"type": "string", "description": "标题/任务号/业务单号关键字"},
            }, []),
        },
        "team_task_summary": {
            "description": "团队任务汇总：未完成、逾期、阻塞、本周完成、按人负载、分析失败数。",
            "parameters": _schema({}, []),
        },
        "update_task": {
            "description": "修改任务的截止时间或优先级（需用户确认）。",
            "parameters": _schema({
                "task_id": _task_id_prop(),
                "due_at": {"type": "string", "description": "新截止时间 ISO 8601"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
            }, ["task_id"]),
        },
        "remind_task": {
            "description": "催办任务（2 小时内去重）。",
            "parameters": _schema({"task_id": _task_id_prop()}, ["task_id"]),
        },
        "reassign_task": {
            "description": "把未完成任务改派给另一个直属子智能体（需用户确认；已完成任务先退回）。",
            "parameters": _schema({
                "task_id": _task_id_prop(),
                "new_assignee_user_id": {"type": "integer", "description": "新接收人用户 ID"},
            }, ["task_id", "new_assignee_user_id"]),
        },
        "cancel_task": {
            "description": "取消未完成任务，必须填写原因（需用户确认）。",
            "parameters": _schema({
                "task_id": _task_id_prop(),
                "reason": {"type": "string", "description": "取消原因"},
            }, ["task_id", "reason"]),
        },
        "return_task": {
            "description": "退回已完成任务让员工重做（需用户确认）。",
            "parameters": _schema({
                "task_id": _task_id_prop(),
                "reason": {"type": "string", "description": "退回原因"},
            }, ["task_id"]),
        },
        "update_subordinate_agent": {
            "description": "配置直属子智能体的能力/数据范围（需用户确认；P1 主管只能配能力）。",
            "parameters": _schema({
                "agent_id": {"type": "integer", "description": "子智能体 ID（与 user_id 二选一）"},
                "user_id": {"type": "integer", "description": "子智能体绑定的用户 ID"},
                "granted": {"type": "array", "items": {"type": "string"}, "description": "授予能力码列表"},
                "disabled": {"type": "array", "items": {"type": "string"}, "description": "禁用能力码列表"},
                "data_scope": {"type": "object", "description": "仅管理员可用；主管 P1 不允许"},
            }, []),
        },
    }


def build_task_tools_schema(allowed_tools: set) -> List[dict]:
    specs = []
    for name, spec in _task_tool_specs().items():
        if name not in allowed_tools:
            continue
        specs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        })
    return specs


def task_tool_infos(allowed_tools: set) -> List[dict]:
    return [
        {"name": name, "description": spec["description"]}
        for name, spec in _task_tool_specs().items()
        if name in allowed_tools
    ]


def is_task_tool(name: str) -> bool:
    return name in TASK_TOOL_NAMES


def requires_confirmation(name: str) -> bool:
    return name in CONFIRM_ACTION_TYPES


def validate_task_tool_input(name: str, args: Optional[dict]) -> Optional[str]:
    args = args if isinstance(args, dict) else {}
    spec = _task_tool_specs().get(name)
    if not spec:
        return f"未知任务工具：{name}"
    for field in spec["parameters"].get("required", []):
        value = args.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"{field} 不能为空"
    if name == "assign_task":
        if args.get("task_type", "general") == "business":
            if not args.get("biz_type") or not args.get("biz_identifier"):
                return "业务任务必须提供 biz_type 和 biz_identifier"
        if not args.get("assignee_user_id") and not args.get("assignee_name"):
            return "必须提供 assignee_user_id 或 assignee_name"
    if name == "add_subordinate" and not args.get("user_id") and not args.get("username"):
        return "必须提供 user_id 或 username"
    if name == "update_subordinate_agent" and not args.get("agent_id") and not args.get("user_id"):
        return "必须提供 agent_id 或 user_id"
    if name == "update_task" and not args.get("due_at") and not args.get("priority"):
        return "due_at 或 priority 至少提供一个"
    return None


def _resolve_child(ctx: AgentContext, args: dict):
    user_id = args.get("assignee_user_id")
    if user_id:
        child = ctx.child_by_user_id(int(user_id))
    else:
        child = ctx.child_by_name(str(args.get("assignee_name") or ""))
    if not child:
        raise task_service.TaskError("只能派发给直属子智能体", 403)
    return child


async def prepare_confirmation(
    db: AsyncSession,
    ctx: AgentContext,
    name: str,
    args: dict,
) -> Dict[str, Any]:
    """校验并生成确认卡数据；不产生业务写入。"""
    invalid = validate_task_tool_input(name, args)
    if invalid:
        raise task_service.TaskError(invalid)

    if name == "assign_task":
        child = _resolve_child(ctx, args)
        task_type = args.get("task_type") or "general"
        preview = {
            "action_type": "assign_task",
            "title": "派发任务",
            "assignee_name": child.display_name,
            "task_title": args.get("title"),
            "due_at": args.get("due_at"),
            "priority": args.get("priority") or "normal",
            "task_type": task_type,
        }
        action_data = {
            "action_type": "assign_task",
            "assignee_user_id": child.user_id,
            "title": args.get("title"),
            "description": args.get("description") or "",
            "due_at": args.get("due_at"),
            "priority": args.get("priority") or "normal",
            "task_type": task_type,
            "biz_type": args.get("biz_type"),
            "biz_identifier": args.get("biz_identifier"),
            "biz_context": args.get("biz_context") or {},
        }
        if task_type == "business":
            from app.services.agent.business import resolve_business_object
            try:
                biz = await resolve_business_object(
                    db, ctx.scope, args.get("biz_type"), args.get("biz_identifier"),
                    args.get("biz_context") or {},
                )
            except Exception as exc:
                raise task_service.TaskError(
                    f"业务对象校验失败：{getattr(exc, 'message', str(exc))}",
                    getattr(exc, "status_code", 400),
                )
            preview.update({"biz_title": biz["biz_title"], "biz_no": biz["biz_no"], "biz_url": biz["biz_url"]})
            action_data.update({
                "biz_id": biz["biz_id"], "biz_no": biz["biz_no"],
                "biz_title": biz["biz_title"], "biz_url": biz["biz_url"],
                "resolved_biz_context": biz.get("biz_context") or {},
            })
        return {"preview": preview, "action_data": action_data}

    if name == "update_task":
        task = await task_service._load_task(db, int(args["task_id"]))
        task_service._ensure_assigner(ctx, task)
        task_service._ensure_open(task, "改期/改优先级")
        return {
            "preview": {
                "action_type": name, "title": "修改任务",
                "task_no": task.task_no, "task_title": task.title,
                "due_at": args.get("due_at"), "priority": args.get("priority"),
            },
            "action_data": {
                "action_type": name, "task_id": task.id,
                "due_at": args.get("due_at"), "priority": args.get("priority"),
            },
        }

    if name == "reassign_task":
        task = await task_service._load_task(db, int(args["task_id"]))
        task_service._ensure_assigner(ctx, task)
        if task.status == "completed":
            raise task_service.TaskError("已完成任务必须先退回，再改派")
        task_service._ensure_open(task, "改派")
        child = ctx.child_by_user_id(int(args["new_assignee_user_id"]))
        if not child:
            raise task_service.TaskError("只能改派给另一个直属子智能体", 403)
        return {
            "preview": {
                "action_type": name, "title": "改派任务",
                "task_no": task.task_no, "task_title": task.title,
                "old_assignee_user_id": task.assignee_user_id,
                "new_assignee_name": child.display_name,
            },
            "action_data": {
                "action_type": name, "task_id": task.id,
                "new_assignee_user_id": child.user_id,
            },
        }

    if name == "cancel_task":
        task = await task_service._load_task(db, int(args["task_id"]))
        task_service._ensure_assigner(ctx, task)
        if task.status == "completed":
            raise task_service.TaskError("已完成任务不能取消")
        task_service._ensure_open(task, "取消")
        return {
            "preview": {
                "action_type": name, "title": "取消任务",
                "task_no": task.task_no, "task_title": task.title,
                "reason": args.get("reason"),
            },
            "action_data": {
                "action_type": name, "task_id": task.id, "reason": args.get("reason"),
            },
        }

    if name == "return_task":
        task = await task_service._load_task(db, int(args["task_id"]))
        task_service._ensure_assigner(ctx, task)
        if task.status != "completed":
            raise task_service.TaskError("只有已完成任务可以退回")
        return {
            "preview": {
                "action_type": name, "title": "退回重做",
                "task_no": task.task_no, "task_title": task.title,
                "reason": args.get("reason"),
            },
            "action_data": {
                "action_type": name, "task_id": task.id, "reason": args.get("reason") or "",
            },
        }

    if name == "submit_task_report":
        task = await task_service._load_task(db, int(args["task_id"]))
        task_service._ensure_assignee(ctx, task)
        if task.status not in task_service.OPEN_STATUSES:
            raise task_service.TaskError(f"当前状态不能提交汇报：{task.status}")
        return {
            "preview": {
                "action_type": name, "title": "提交任务汇报",
                "task_no": task.task_no, "task_title": task.title,
                "summary": args.get("summary"),
            },
            "action_data": {
                "action_type": name, "task_id": task.id,
                "summary": args.get("summary"),
                "result_data": args.get("result_data"),
                "evidence": args.get("evidence"),
            },
        }

    if name == "add_subordinate":
        target = None
        if args.get("user_id"):
            target = await db.get(SysUser, int(args["user_id"]))
        elif args.get("username"):
            target = (await db.execute(
                select(SysUser).where(SysUser.username == args["username"])
            )).scalars().first()
        if not target:
            raise task_service.TaskError("目标用户不存在", 404)
        return {
            "preview": {
                "action_type": name, "title": "添加直属成员",
                "target_name": target.display_name or target.username,
                "username": target.username,
            },
            "action_data": {
                "action_type": name, "target_user_id": target.id,
                "target_username": target.username,
            },
        }

    if name == "update_subordinate_agent":
        target_agent, target_user = await _resolve_target_agent(db, ctx, args)
        return {
            "preview": {
                "action_type": name, "title": "配置子智能体",
                "agent_id": target_agent.id,
                "agent_name": target_agent.display_name,
                "user_name": target_user.display_name or target_user.username,
                "granted": args.get("granted"),
                "disabled": args.get("disabled"),
                "data_scope": args.get("data_scope"),
            },
            "action_data": {
                "action_type": name, "agent_id": target_agent.id,
                "granted": args.get("granted"),
                "disabled": args.get("disabled"),
                "data_scope": args.get("data_scope"),
            },
        }

    raise task_service.TaskError(f"不支持的确认动作：{name}")


async def _resolve_target_agent(db: AsyncSession, ctx: AgentContext, args: dict):
    if args.get("agent_id"):
        agent = await db.get(Agent, int(args["agent_id"]))
        if not agent or int(agent.parent_agent_id or 0) != int(ctx.agent.id):
            raise task_service.TaskError("只能配置直属子智能体", 403)
        user = await db.get(SysUser, agent.user_id)
        if not user:
            raise task_service.TaskError("子智能体用户不存在", 404)
        return agent, user
    child = ctx.child_by_user_id(int(args["user_id"]))
    if not child:
        raise task_service.TaskError("只能配置直属子智能体", 403)
    agent = await db.get(Agent, child.agent_id)
    user = await db.get(SysUser, child.user_id)
    return agent, user


async def execute_direct_tool(db: AsyncSession, ctx: AgentContext, name: str, args: dict) -> Dict[str, Any]:
    if name == "list_my_tasks":
        return await task_service.list_my_tasks(
            db, ctx, status=args.get("status") or "", keyword=args.get("keyword") or "", page_size=20,
        )
    if name == "get_task_detail":
        return await task_service.task_detail(db, ctx, int(args["task_id"]))
    if name == "start_task":
        return await task_service.start_task(db, ctx, int(args["task_id"]))
    if name == "block_task":
        return await task_service.block_task(db, ctx, int(args["task_id"]), args.get("reason") or "")
    if name == "analyze_task":
        return await task_service.queue_manual_analysis(db, ctx, int(args["task_id"]))
    if name == "remind_task":
        return await task_service.remind_task(db, ctx, int(args["task_id"]))
    if name == "list_my_subordinates":
        return {"items": [
            {
                "agent_id": c.agent_id, "user_id": c.user_id,
                "name": c.display_name, "username": c.username, "status": c.status,
            }
            for c in ctx.children
        ]}
    if name == "list_team_tasks":
        return await task_service.list_team_tasks(
            db, ctx,
            status=args.get("status") or "",
            keyword=args.get("keyword") or "",
            assignee_user_id=args.get("assignee_user_id"),
            page_size=20,
        )
    if name == "team_task_summary":
        return await task_service.team_task_summary(db, ctx)
    raise task_service.TaskError(f"未知任务工具：{name}")


async def execute_confirmed_action(
    db: AsyncSession,
    *,
    user_id: int,
    action_data: dict,
    expected_agent_id: Optional[int] = None,
) -> dict:
    """确认后执行任务/团队动作；重新加载上下文，实时校验权限与状态。"""
    user = await db.get(SysUser, int(user_id))
    if not user or not user.is_active:
        raise task_service.TaskError("用户不存在或已停用", 403)
    ctx = await load_agent_context(db, user, use_cache=False)
    if expected_agent_id and int(ctx.agent.id) != int(expected_agent_id):
        raise task_service.TaskError("确认单与当前智能体不匹配，请重新发起", 403)
    name = action_data.get("action_type")
    if name == "assign_task":
        task = await task_service.create_task(
            db, ctx,
            assignee_user_id=int(action_data["assignee_user_id"]),
            title=action_data.get("title") or "",
            description=action_data.get("description") or "",
            due_at=action_data.get("due_at"),
            priority=action_data.get("priority") or "normal",
            task_type=action_data.get("task_type") or "general",
            biz_type=action_data.get("biz_type"),
            biz_identifier=action_data.get("biz_identifier"),
            biz_context=action_data.get("resolved_biz_context") or action_data.get("biz_context") or {},
        )
        return {"task": task_service.task_to_dict(task)}
    if name == "update_task":
        task = await task_service.update_task(
            db, ctx, int(action_data["task_id"]),
            due_at=action_data.get("due_at"), priority=action_data.get("priority"),
        )
        return {"task": task}
    if name == "reassign_task":
        task = await task_service.reassign_task(
            db, ctx, int(action_data["task_id"]), int(action_data["new_assignee_user_id"]),
        )
        return {"task": task}
    if name == "cancel_task":
        task = await task_service.cancel_task(
            db, ctx, int(action_data["task_id"]), action_data.get("reason") or "",
        )
        return {"task": task}
    if name == "return_task":
        task = await task_service.return_task(
            db, ctx, int(action_data["task_id"]), action_data.get("reason") or "",
        )
        return {"task": task}
    if name == "submit_task_report":
        task = await task_service.submit_report(
            db, ctx, int(action_data["task_id"]),
            summary=action_data.get("summary") or "",
            result_data=action_data.get("result_data"),
            evidence=action_data.get("evidence"),
        )
        return {"task": task}
    if name == "add_subordinate":
        result = await hierarchy.add_subordinate(
            db, ctx, user_id=int(action_data["target_user_id"]),
        )
        return {"subordinate": result}
    if name == "update_subordinate_agent":
        target_agent, _ = await _resolve_target_agent(db, ctx, action_data)
        saved = await policy.update_agent_policy(
            db,
            operator_ctx=ctx,
            target_agent=target_agent,
            granted=action_data.get("granted"),
            disabled=action_data.get("disabled"),
            data_scope=action_data.get("data_scope"),
            reason="助手对话配置",
            is_admin=ctx.role_code == "admin",
        )
        return {"policy": saved, "agent_id": target_agent.id}
    raise task_service.TaskError(f"不支持的确认动作：{name}")
