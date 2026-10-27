"""智能体中心 API：我的智能体、任务、团队与管理台。"""

import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.agent.agent import Agent
from app.models.agent.conversation import AgentConversation
from app.models.agent.task import AgentTask
from app.models.basicdata.ai_agent import AssistantRun
from app.models.basicdata.user import SysUser
from app.services.agent import conversation as conversation_service
from app.services.agent import hierarchy, policy, task_service
from app.services.agent.capabilities import (
    CONFIGURABLE_CAPABILITIES,
    baseline_capabilities,
    public_catalog,
)
from app.services.agent.context import load_agent_context

logger = logging.getLogger(__name__)

router = APIRouter()


def _user_id(current_user: dict) -> int:
    return int(current_user.get("user_id") or current_user.get("sub"))


async def _load_user(db: AsyncSession, current_user: dict) -> SysUser:
    if not get_settings().AGENT_TASK_ENABLED:
        raise task_service.TaskError("智能体中心未启用", 403)
    user = await db.get(SysUser, _user_id(current_user))
    if not user:
        raise task_service.TaskError("用户不存在", 401)
    return user


def _ok(data: Any = None, message: str = "") -> dict:
    return {"code": 0, "message": message, "data": data}


def _err(message: str, code: int = 400) -> dict:
    return {"code": code, "message": message, "data": None}


def _capture(exc: Exception) -> dict:
    status = getattr(exc, "status_code", None)
    message = getattr(exc, "message", None) or str(exc)
    if status is None:
        logger.exception("[agent-api] 未预期异常: %s", exc)
    return _err(message, int(status or 400))


def _agent_brief(agent: Agent, user: SysUser) -> dict:
    return {
        "id": agent.id,
        "agent_no": agent.agent_no,
        "user_id": agent.user_id,
        "username": user.username,
        "display_name": agent.display_name,
        "status": agent.status,
        "parent_agent_id": agent.parent_agent_id,
        "config_version": agent.config_version,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def _scope_payload(ctx) -> dict:
    return {
        "summary": ctx.scope.summary() if ctx.scope else "",
        "org_ids": sorted(ctx.effective_org_ids),
        "org_names": sorted(ctx.scope.org_names) if ctx.scope else [],
        "include_self_owned": True,
    }


def _capability_items(capabilities: set) -> List[dict]:
    return [
        {"code": code, "name": CONFIGURABLE_CAPABILITIES[code].name,
         "category": CONFIGURABLE_CAPABILITIES[code].category}
        for code in sorted(capabilities) if code in CONFIGURABLE_CAPABILITIES
    ]


class AddMemberIn(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None


class PolicyIn(BaseModel):
    granted: Optional[List[str]] = None
    disabled: Optional[List[str]] = None
    data_scope: Optional[dict] = None
    reason: str = ""


class HierarchyIn(BaseModel):
    action: str = Field(..., description="reparent|unbind|lock|unlock")
    new_parent_id: Optional[int] = None
    reason: str = ""


class TaskBlockIn(BaseModel):
    reason: str


class TaskSubmitIn(BaseModel):
    summary: str
    result_data: Optional[dict] = None
    evidence: Optional[list] = None


class TaskPatchIn(BaseModel):
    due_at: Optional[str] = None
    priority: Optional[str] = None


class TaskReassignIn(BaseModel):
    new_assignee_user_id: int


class TaskCancelIn(BaseModel):
    reason: str


class TaskReturnIn(BaseModel):
    reason: str = ""


# ───────────────────────────── 我的 ─────────────────────────────

@router.get("/me")
async def my_agent(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        summary = await task_service.my_task_summary(db, ctx)
        week_start = datetime.now() - timedelta(days=7)
        usage = (await db.execute(
            select(func.count(AssistantRun.id), func.coalesce(func.sum(AssistantRun.total_tokens), 0))
            .where(AssistantRun.user_id == str(user.id), AssistantRun.created_at >= week_start)
        )).first()
        parent = await db.get(Agent, ctx.agent.parent_agent_id) if ctx.agent.parent_agent_id else None
        return _ok({
            "agent": _agent_brief(ctx.agent, user),
            "display_name": ctx.display_name,
            "parent_agent_id": ctx.agent.parent_agent_id,
            "parent_display_name": parent.display_name if parent else None,
            "is_supervisor": ctx.is_supervisor,
            "has_assigned_tasks": ctx.has_assigned_tasks,
            "children_count": len(ctx.children),
            "effective_capabilities": _capability_items(ctx.effective_capabilities),
            "scope": _scope_payload(ctx),
            "policy": policy.normalize_policy(ctx.agent.capability_policy),
            "task_summary": summary,
            "usage_7d": {
                "runs": int(usage[0] or 0) if usage else 0,
                "total_tokens": int(usage[1] or 0) if usage else 0,
            },
            "capability_catalog": public_catalog(),
        })
    except Exception as exc:
        return _capture(exc)


@router.get("/me/conversations")
async def my_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await conversation_service.list_conversations(
            db, agent_id=ctx.agent.id, user_id=user.id, page=page, page_size=page_size,
        ))
    except Exception as exc:
        return _capture(exc)


@router.get("/me/conversations/{conversation_id}")
async def my_conversation_detail(
    conversation_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        conversation = await conversation_service.get_owned_conversation(
            db, conversation_id, user_id=user.id, agent_id=ctx.agent.id,
        )
        return _ok(await conversation_service.conversation_messages(db, conversation, limit))
    except Exception as exc:
        return _capture(exc)


@router.post("/me/conversations/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        conversation = await conversation_service.get_owned_conversation(
            db, conversation_id, user_id=user.id, agent_id=ctx.agent.id,
        )
        return _ok(await conversation_service.archive_conversation(db, conversation))
    except Exception as exc:
        return _capture(exc)


@router.get("/me/tasks")
async def my_tasks(
    status: str = "",
    keyword: str = "",
    priority: str = "",
    due_from: Optional[str] = None,
    due_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.list_my_tasks(
            db, ctx, status=status, keyword=keyword, priority=priority,
            due_from=datetime.fromisoformat(due_from) if due_from else None,
            due_to=datetime.fromisoformat(due_to) if due_to else None,
            page=page, page_size=page_size,
        ))
    except Exception as exc:
        return _capture(exc)


@router.get("/me/tasks/summary")
async def my_tasks_summary(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.my_task_summary(db, ctx))
    except Exception as exc:
        return _capture(exc)


# ───────────────────────────── 团队 ─────────────────────────────

@router.get("/me/team")
async def my_team(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        items = []
        for child in ctx.children:
            child_user = await db.get(SysUser, child.user_id)
            if not child_user:
                continue
            child_ctx = await load_agent_context(db, child_user)
            open_count = int((await db.execute(
                select(func.count(AgentTask.id)).where(
                    AgentTask.assignee_agent_id == child.agent_id,
                    AgentTask.status.in_(task_service.OPEN_STATUSES),
                )
            )).scalar() or 0)
            overdue = int((await db.execute(
                select(func.count(AgentTask.id)).where(
                    AgentTask.assignee_agent_id == child.agent_id,
                    AgentTask.status.in_(task_service.OPEN_STATUSES),
                    AgentTask.due_at < datetime.now(),
                )
            )).scalar() or 0)
            items.append({
                **_agent_brief(child_ctx.agent, child_user),
                "name": child.display_name,
                "username": child.username,
                "effective_capabilities": _capability_items(child_ctx.effective_capabilities),
                "scope": _scope_payload(child_ctx),
                "open_task_count": open_count,
                "overdue_task_count": overdue,
            })
        return _ok({"items": items, "total": len(items)})
    except Exception as exc:
        return _capture(exc)


@router.post("/me/team")
async def add_team_member(
    body: AddMemberIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        result = await hierarchy.add_subordinate(
            db, ctx, user_id=body.user_id, username=body.username or "",
        )
        return _ok(result, "已添加并通知对方")
    except Exception as exc:
        return _capture(exc)


@router.get("/me/team/candidates")
async def team_candidates(
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        await _load_user(db, current_user)
        return _ok({"items": await hierarchy.list_candidates(db, keyword)})
    except Exception as exc:
        return _capture(exc)


@router.get("/me/team/tasks")
async def team_tasks(
    status: str = "",
    keyword: str = "",
    assignee_user_id: Optional[int] = None,
    priority: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.list_team_tasks(
            db, ctx, status=status, keyword=keyword,
            assignee_user_id=assignee_user_id, priority=priority,
            page=page, page_size=page_size,
        ))
    except Exception as exc:
        return _capture(exc)


@router.get("/me/team/tasks/summary")
async def team_tasks_summary(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.team_task_summary(db, ctx))
    except Exception as exc:
        return _capture(exc)


@router.get("/me/team/{agent_id}")
async def team_member_detail(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        child = await db.get(Agent, agent_id)
        if not child or int(child.parent_agent_id or 0) != int(ctx.agent.id):
            return _err("只能查看直属子智能体", 403)
        child_user = await db.get(SysUser, child.user_id)
        child_ctx = await load_agent_context(db, child_user)
        child_policy = policy.normalize_policy(child.capability_policy)
        role_baseline = baseline_capabilities(child_ctx.permissions)
        effective = child_ctx.effective_capabilities
        catalog = []
        for item in public_catalog():
            code = item["code"]
            if not item.get("grantable"):
                continue
            catalog.append({
                **item,
                "role_owned": code in role_baseline,
                "granted": code in (child_policy.get("granted") or []),
                "disabled": code in (child_policy.get("disabled") or []),
                "effective": code in effective,
                "grantable_now": code in ctx.effective_capabilities,
            })
        return _ok({
            "agent": _agent_brief(child, child_user),
            "policy": child_policy,
            "scope": _scope_payload(child_ctx),
            "effective_capabilities": _capability_items(effective),
            "role_baseline": _capability_items(role_baseline),
            "grantable": _capability_items(ctx.effective_capabilities),
            "catalog": catalog,
        })
    except Exception as exc:
        return _capture(exc)


@router.put("/me/team/{agent_id}/policy")
async def update_team_policy(
    agent_id: int,
    body: PolicyIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.team", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        target = await db.get(Agent, agent_id)
        if not target:
            return _err("智能体不存在", 404)
        saved = await policy.update_agent_policy(
            db, operator_ctx=ctx, target_agent=target,
            granted=body.granted, disabled=body.disabled, data_scope=body.data_scope,
            reason=body.reason, is_admin=False,
        )
        return _ok(saved, "配置已保存并通知对方")
    except Exception as exc:
        return _capture(exc)


# ───────────────────────────── 任务 ─────────────────────────────

@router.get("/tasks/{task_id}")
async def task_detail(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.task_detail(db, ctx, task_id))
    except Exception as exc:
        return _capture(exc)


@router.get("/tasks/{task_id}/events")
async def task_events(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        detail = await task_service.task_detail(db, ctx, task_id)
        return _ok({"items": detail["events"]})
    except Exception as exc:
        return _capture(exc)


@router.get("/tasks/{task_id}/reports")
async def task_reports(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        detail = await task_service.task_detail(db, ctx, task_id)
        return _ok({"items": detail["reports"]})
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/start")
async def start_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.start_task(db, ctx, task_id))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/block")
async def block_task(
    task_id: int,
    body: TaskBlockIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.block_task(db, ctx, task_id, body.reason))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.resume_task(db, ctx, task_id))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/submit")
async def submit_task(
    task_id: int,
    body: TaskSubmitIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.submit_report(
            db, ctx, task_id, summary=body.summary,
            result_data=body.result_data, evidence=body.evidence,
        ))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/analyze")
async def analyze_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.queue_manual_analysis(db, ctx, task_id))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/remind")
async def remind_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.remind_task(db, ctx, task_id))
    except Exception as exc:
        return _capture(exc)


@router.patch("/tasks/{task_id}")
async def patch_task(
    task_id: int,
    body: TaskPatchIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.update_task(
            db, ctx, task_id, due_at=body.due_at, priority=body.priority,
        ))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/reassign")
async def reassign_task(
    task_id: int,
    body: TaskReassignIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.reassign_task(
            db, ctx, task_id, body.new_assignee_user_id,
        ))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: int,
    body: TaskCancelIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.cancel_task(db, ctx, task_id, body.reason))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/return")
async def return_task(
    task_id: int,
    body: TaskReturnIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        return _ok(await task_service.return_task(db, ctx, task_id, body.reason))
    except Exception as exc:
        return _capture(exc)


@router.post("/tasks/{task_id}/conversation")
async def task_conversation(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.self", "read")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user)
        await task_service.build_task_context(db, task_id, user.id)
        conversation = await conversation_service.get_or_create_task_conversation(
            db, agent=ctx.agent, user_id=user.id, task_id=task_id,
        )
        return _ok({"conversation_id": conversation.id, "task_id": task_id})
    except Exception as exc:
        return _capture(exc)


# ───────────────────────────── 管理员 ─────────────────────────────

@router.get("/admin/agents")
async def admin_agents(
    keyword: str = "",
    status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        conditions = []
        if status:
            conditions.append(Agent.status == status)
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(SysUser.username.ilike(like), SysUser.display_name.ilike(like),
                                  Agent.agent_no.ilike(like)))
        total = int((await db.execute(
            select(func.count(Agent.id)).select_from(Agent)
            .join(SysUser, SysUser.id == Agent.user_id).where(*conditions)
        )).scalar() or 0)
        rows = (await db.execute(
            select(Agent, SysUser).join(SysUser, SysUser.id == Agent.user_id)
            .where(*conditions)
            .order_by(Agent.id.asc())
            .offset((page - 1) * page_size).limit(page_size)
        )).all()
        items = []
        for agent, user in rows:
            child_count = int((await db.execute(
                select(func.count(Agent.id)).where(Agent.parent_agent_id == agent.id)
            )).scalar() or 0)
            items.append({
                **_agent_brief(agent, user),
                "children_count": child_count,
                "policy": policy.normalize_policy(agent.capability_policy),
            })
        return _ok({"items": items, "total": total, "page": page, "page_size": page_size})
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/tasks")
async def admin_tasks(
    status: str = "",
    keyword: str = "",
    analysis_status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        conditions = []
        if status:
            conditions.append(AgentTask.status.in_([s.strip() for s in status.split(",") if s.strip()]))
        if analysis_status:
            conditions.append(AgentTask.analysis_status == analysis_status)
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(AgentTask.title.ilike(like), AgentTask.task_no.ilike(like),
                                  AgentTask.biz_no.ilike(like)))
        total = int((await db.execute(
            select(func.count(AgentTask.id)).where(*conditions)
        )).scalar() or 0)
        rows = (await db.execute(
            select(AgentTask).where(*conditions).order_by(AgentTask.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        names = await task_service.display_names(db, rows)
        return _ok({
            "items": [
                task_service.task_to_dict(
                    row, assignee_name=names.get(row.assignee_user_id, ""),
                    assigner_name=names.get(row.assigner_user_id, ""),
                )
                for row in rows
            ],
            "total": total, "page": page, "page_size": page_size,
        })
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        agent_count = int((await db.execute(select(func.count(Agent.id)))).scalar() or 0)
        active_agents = int((await db.execute(
            select(func.count(Agent.id)).where(Agent.status == "active")
        )).scalar() or 0)
        status_rows = (await db.execute(
            select(AgentTask.status, func.count(AgentTask.id)).group_by(AgentTask.status)
        )).all()
        analysis_failed = int((await db.execute(
            select(func.count(AgentTask.id)).where(AgentTask.analysis_status == "failed")
        )).scalar() or 0)
        return _ok({
            "agents": agent_count,
            "active_agents": active_agents,
            "tasks_by_status": {row[0]: int(row[1]) for row in status_rows},
            "analysis_failed": analysis_failed,
        })
    except Exception as exc:
        return _capture(exc)


@router.put("/admin/agents/{agent_id}/hierarchy")
async def admin_hierarchy(
    agent_id: int,
    body: HierarchyIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        actor = await _load_user(db, current_user)
        result = await hierarchy.admin_change_hierarchy(
            db, actor=actor, target_agent_id=agent_id,
            action=body.action, new_parent_id=body.new_parent_id, reason=body.reason,
        )
        return _ok(result)
    except Exception as exc:
        return _capture(exc)


@router.put("/admin/agents/{agent_id}/policy")
async def admin_policy(
    agent_id: int,
    body: PolicyIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        user = await _load_user(db, current_user)
        ctx = await load_agent_context(db, user, use_cache=False)
        target = await db.get(Agent, agent_id)
        if not target:
            return _err("智能体不存在", 404)
        saved = await policy.update_agent_policy(
            db, operator_ctx=ctx, target_agent=target,
            granted=body.granted, disabled=body.disabled, data_scope=body.data_scope,
            reason=body.reason, is_admin=True,
        )
        return _ok(saved, "配置已保存并通知对方")
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/conversations/{conversation_id}")
async def admin_conversation(
    conversation_id: int,
    reason: str = Query(..., min_length=2),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        actor = await _load_user(db, current_user)
        conversation = await db.get(AgentConversation, conversation_id)
        if not conversation:
            return _err("会话不存在", 404)
        target_user = await db.get(SysUser, conversation.user_id)
        target_label = (
            f"{target_user.username}(id={target_user.id})" if target_user else f"id={conversation.user_id}"
        )
        await log_audit(
            db, "agent_conversation", conversation.id, "view",
            field_name="reason", new_value=f"{reason}；目标用户 {target_label}",
            operator=actor.display_name or actor.username,
        )
        data = await conversation_service.conversation_messages(db, conversation, limit)
        data.update({
            "target_user_id": conversation.user_id,
            "target_username": target_user.username if target_user else None,
            "reason": reason,
            "viewed_by": actor.username,
        })
        return _ok(data)
    except Exception as exc:
        return _capture(exc)
