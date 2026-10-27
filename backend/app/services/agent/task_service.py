"""主管任务闭环：任务账本、状态机、汇报、事件与通知。"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import get_command_client, note_failure, note_success
from app.models.agent.task import AgentTask, AgentTaskEvent, AgentTaskReport
from app.models.basicdata.user import SysUser
from app.services.agent.business import BusinessObjectError, resolve_business_object
from app.services.agent.context import AgentContext, load_agent_context
from app.services.agent.errors import AgentError
from app.services.agent.notify import notify_user
from app.services.agent.sequence import next_serial_id

logger = logging.getLogger(__name__)

OPEN_STATUSES = ("pending", "in_progress", "blocked")
TASK_STATUSES = ("pending", "in_progress", "blocked", "completed", "cancelled")
PRIORITIES = ("low", "normal", "high", "urgent")
MANUAL_REMIND_TTL_S = 2 * 3600
REANALYZE_KEY_TTL_S = 3600

_memory_dedupe: Dict[str, float] = {}


class TaskError(AgentError):
    pass


def _now() -> datetime:
    return datetime.now()


def _to_naive_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def parse_due_at(value) -> datetime:
    if isinstance(value, datetime):
        return _to_naive_local(value)
    raw = str(value or "").strip()
    if not raw:
        raise TaskError("截止时间不能为空")
    normalized = raw.replace("Z", "+00:00")
    try:
        return _to_naive_local(datetime.fromisoformat(normalized))
    except ValueError:
        raise TaskError("截止时间格式错误，需 ISO 8601（如 2026-10-30T18:00:00）")


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _is_overdue(task: AgentTask) -> bool:
    return bool(task.due_at and task.due_at < _now() and task.status in OPEN_STATUSES)


def task_to_dict(task: AgentTask, *, assignee_name: str = "", assigner_name: str = "") -> dict:
    return {
        "id": task.id,
        "task_no": task.task_no,
        "title": task.title,
        "description": task.description,
        "task_type": task.task_type,
        "biz_type": task.biz_type,
        "biz_id": task.biz_id,
        "biz_no": task.biz_no,
        "biz_title": task.biz_title,
        "biz_url": task.biz_url,
        "biz_context": task.biz_context,
        "assigner_agent_id": task.assigner_agent_id,
        "assigner_user_id": task.assigner_user_id,
        "assigner_name": assigner_name,
        "assignee_agent_id": task.assignee_agent_id,
        "assignee_user_id": task.assignee_user_id,
        "assignee_name": assignee_name,
        "priority": task.priority,
        "status": task.status,
        "source": task.source,
        "due_at": _iso(task.due_at),
        "started_at": _iso(task.started_at),
        "completed_at": _iso(task.completed_at),
        "cancelled_at": _iso(task.cancelled_at),
        "analysis_status": task.analysis_status,
        "analysis_error": task.analysis_error,
        "analysis_finished_at": _iso(task.analysis_finished_at),
        "latest_report_id": task.latest_report_id,
        "reopen_count": task.reopen_count,
        "is_overdue": _is_overdue(task),
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }


async def display_names(db: AsyncSession, tasks: Iterable[AgentTask]) -> Dict[int, str]:
    user_ids = set()
    for task in tasks:
        user_ids.add(task.assigner_user_id)
        user_ids.add(task.assignee_user_id)
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(SysUser.id, SysUser.display_name, SysUser.username).where(SysUser.id.in_(user_ids))
    )).all()
    return {int(uid): (display or username) for uid, display, username in rows}


def task_path(task_id: int) -> str:
    return f"/agents/tasks/{task_id}"


async def _load_task(db: AsyncSession, task_id: int, *, for_update: bool = False) -> AgentTask:
    stmt = select(AgentTask).where(AgentTask.id == int(task_id))
    if for_update:
        stmt = stmt.with_for_update()
    task = (await db.execute(stmt)).scalars().first()
    if not task:
        raise TaskError("任务不存在", 404)
    return task


def _is_admin(ctx: AgentContext) -> bool:
    return ctx.role_code == "admin"


def _ensure_participant(ctx: AgentContext, task: AgentTask) -> None:
    if _is_admin(ctx):
        return
    if int(ctx.user.id) not in (int(task.assigner_user_id), int(task.assignee_user_id)):
        raise TaskError("无权查看该任务", 403)


def _ensure_assignee(ctx: AgentContext, task: AgentTask) -> None:
    if int(ctx.user.id) != int(task.assignee_user_id):
        raise TaskError("只有任务接收人可以执行该操作", 403)


def _ensure_assigner(ctx: AgentContext, task: AgentTask) -> None:
    if not _is_admin(ctx) and int(ctx.user.id) != int(task.assigner_user_id):
        raise TaskError("只有任务派发人可以执行该操作", 403)


def _ensure_open(task: AgentTask, action: str) -> None:
    if task.status not in OPEN_STATUSES:
        raise TaskError(f"{action}只允许待处理/处理中/阻塞任务，当前状态：{task.status}")


async def _add_event(
    db: AsyncSession,
    task: AgentTask,
    event_type: str,
    *,
    actor_ctx: Optional[AgentContext] = None,
    actor_user_id: Optional[int] = None,
    from_status: Optional[str] = None,
    to_status: Optional[str] = None,
    payload: Optional[dict] = None,
) -> AgentTaskEvent:
    event = AgentTaskEvent(
        task_id=task.id,
        event_type=event_type,
        actor_agent_id=actor_ctx.agent.id if actor_ctx else None,
        actor_user_id=actor_user_id or (actor_ctx.user.id if actor_ctx else None),
        from_status=from_status,
        to_status=to_status,
        payload=payload,
    )
    db.add(event)
    await db.flush()
    return event


async def _open_task_count(db: AsyncSession, user_id: int) -> int:
    return int((await db.execute(
        select(func.count(AgentTask.id)).where(
            AgentTask.assignee_user_id == int(user_id),
            AgentTask.status.in_(OPEN_STATUSES),
        )
    )).scalar() or 0)


async def _redis_set_nx(key: str, ttl: int) -> bool:
    """返回 True 表示首次获取；Redis 不可用时用进程内 TTL 兜底，避免每分钟重复提醒。"""
    client = get_command_client()
    if client is not None:
        try:
            ok = await client.set(key, "1", nx=True, ex=ttl)
            note_success()
            return bool(ok)
        except Exception as exc:
            note_failure()
            logger.warning("[agent-task] Redis 去重失败（降级内存） key=%s: %s", key, exc)
    now = _now().timestamp()
    expires = _memory_dedupe.get(key)
    if expires and expires > now:
        return False
    for stale_key in [k for k, exp in _memory_dedupe.items() if exp <= now]:
        _memory_dedupe.pop(stale_key, None)
    _memory_dedupe[key] = now + ttl
    return True


async def create_task(
    db: AsyncSession,
    ctx: AgentContext,
    *,
    assignee_user_id: int,
    title: str,
    description: str = "",
    due_at,
    priority: str = "normal",
    task_type: str = "general",
    biz_type: Optional[str] = None,
    biz_identifier: Optional[str] = None,
    biz_context: Optional[dict] = None,
    source: str = "supervisor_chat",
) -> AgentTask:
    """创建任务：仅直属子智能体；业务任务双端可见性校验。"""
    child = ctx.child_by_user_id(assignee_user_id)
    if not child:
        raise TaskError("只能派发给直属子智能体", 403)
    if child.status != "active":
        raise TaskError("子智能体已禁用，请先启用或选择其他成员", 400)
    if ctx.scope is None:
        ctx = await load_agent_context(db, ctx.user, use_cache=False)

    title = (title or "").strip()
    if not title:
        raise TaskError("任务标题不能为空")
    if len(title) > 200:
        raise TaskError("任务标题不能超过 200 字")
    if priority not in PRIORITIES:
        raise TaskError(f"优先级非法：{priority}")
    if task_type not in ("business", "general"):
        raise TaskError(f"任务类型非法：{task_type}")
    due = parse_due_at(due_at)

    max_open = int(get_settings().AGENT_TASK_MAX_OPEN_PER_USER)
    if await _open_task_count(db, child.user_id) >= max_open:
        raise TaskError(f"该成员未完成任务已达上限 {max_open} 个，请先完成或取消部分任务", 400)

    biz = await _resolve_task_business(
        db, ctx, child, task_type, biz_type, biz_identifier, biz_context or {},
    )

    next_id = await next_serial_id(db, "agent_task")
    task = AgentTask(
        id=next_id,
        task_no=f"AT-{next_id:06d}",
        title=title,
        description=(description or "").strip() or None,
        task_type=task_type,
        biz_type=biz["biz_type"] if biz else None,
        biz_id=biz["biz_id"] if biz else None,
        biz_no=biz["biz_no"] if biz else None,
        biz_context=biz.get("biz_context") if biz else None,
        biz_title=biz["biz_title"] if biz else None,
        biz_url=biz["biz_url"] if biz else None,
        assigner_agent_id=ctx.agent.id,
        assigner_user_id=int(ctx.user.id),
        assignee_agent_id=child.agent_id,
        assignee_user_id=int(child.user_id),
        priority=priority,
        status="pending",
        source=source,
        due_at=due,
        analysis_status="pending" if task_type == "business" else "skipped",
    )
    db.add(task)
    await db.flush()
    await _add_event(
        db, task, "created", actor_ctx=ctx,
        to_status="pending",
        payload={
            "title": title,
            "priority": priority,
            "due_at": _iso(due),
            "task_type": task_type,
            "biz_no": task.biz_no,
        },
    )
    await notify_user(
        db,
        user_id=child.user_id,
        title=f"[任务]你收到新任务：{title}",
        content=f"派发人：{ctx.user.display_name or ctx.user.username}；截止：{due.strftime('%Y-%m-%d %H:%M')}",
        notif_type="agent_task",
        ref_type="agent_task",
        ref_id=task.id,
        ref_no=task.task_no,
        priority="important" if priority in ("high", "urgent") else "normal",
        sender_id=ctx.user.id,
        sender_name=ctx.user.display_name or ctx.user.username,
        wecom_path=task_path(task.id),
        wecom=True,
    )
    await db.refresh(task)
    return task


async def _resolve_task_business(
    db: AsyncSession,
    ctx: AgentContext,
    child,
    task_type: str,
    biz_type: Optional[str],
    biz_identifier: Optional[str],
    biz_context: dict,
) -> Optional[dict]:
    if task_type != "business":
        return None
    if not biz_type or not biz_identifier:
        raise TaskError("业务任务必须指定业务对象")
    try:
        biz = await resolve_business_object(db, ctx.scope, biz_type, biz_identifier, biz_context)
    except BusinessObjectError as exc:
        raise TaskError(f"主管不可见业务对象：{exc.message}", exc.status_code)

    target_ctx = await load_agent_context(db, await _load_child_user(db, child), use_cache=False)
    required_capability = {
        "order": "query.orders",
        "material_shortage": "query.materials",
        "quality_issue": "query.quality",
    }.get(biz_type)
    if required_capability and required_capability not in target_ctx.effective_capabilities:
        raise TaskError("子智能体缺少该业务域的只读能力，请主管先配置能力或改用通用待办", 403)
    try:
        await resolve_business_object(
            db, target_ctx.scope, biz_type,
            biz["biz_no"] if biz_type != "material_shortage" else str(biz["biz_id"]),
            biz.get("biz_context") or {},
        )
    except BusinessObjectError as exc:
        raise TaskError(f"子智能体不可见业务对象：{exc.message}", exc.status_code)
    return biz


async def _load_child_user(db: AsyncSession, child) -> SysUser:
    user = await db.get(SysUser, child.user_id)
    if not user:
        raise TaskError("任务接收人不存在", 404)
    return user


async def list_my_tasks(
    db: AsyncSession,
    ctx: AgentContext,
    *,
    status: str = "",
    keyword: str = "",
    priority: str = "",
    due_from: Optional[datetime] = None,
    due_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    conditions = [AgentTask.assignee_agent_id == ctx.agent.id]
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            conditions.append(AgentTask.status.in_(statuses))
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(or_(
            AgentTask.title.ilike(like),
            AgentTask.task_no.ilike(like),
            AgentTask.biz_no.ilike(like),
        ))
    if priority:
        conditions.append(AgentTask.priority == priority)
    if due_from:
        conditions.append(AgentTask.due_at >= due_from)
    if due_to:
        conditions.append(AgentTask.due_at <= due_to)

    total = int((await db.execute(
        select(func.count(AgentTask.id)).where(*conditions)
    )).scalar() or 0)
    rows = (await db.execute(
        select(AgentTask)
        .where(*conditions)
        .order_by(AgentTask.status.in_(OPEN_STATUSES).desc(), AgentTask.due_at.asc(), AgentTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()
    names = await display_names(db, rows)
    return {
        "items": [
            task_to_dict(
                row,
                assignee_name=names.get(row.assignee_user_id, ""),
                assigner_name=names.get(row.assigner_user_id, ""),
            )
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def my_task_summary(db: AsyncSession, ctx: AgentContext) -> dict:
    rows = (await db.execute(
        select(AgentTask.status, func.count(AgentTask.id))
        .where(AgentTask.assignee_agent_id == ctx.agent.id)
        .group_by(AgentTask.status)
    )).all()
    by_status = {status: int(count) for status, count in rows}
    overdue = int((await db.execute(
        select(func.count(AgentTask.id)).where(
            AgentTask.assignee_agent_id == ctx.agent.id,
            AgentTask.status.in_(OPEN_STATUSES),
            AgentTask.due_at < _now(),
        )
    )).scalar() or 0)
    week_start = _now() - timedelta(days=7)
    completed_week = int((await db.execute(
        select(func.count(AgentTask.id)).where(
            AgentTask.assignee_agent_id == ctx.agent.id,
            AgentTask.status == "completed",
            AgentTask.completed_at >= week_start,
        )
    )).scalar() or 0)
    return {
        "total": sum(by_status.values()),
        "by_status": {status: by_status.get(status, 0) for status in TASK_STATUSES},
        "open": sum(by_status.get(status, 0) for status in OPEN_STATUSES),
        "overdue": overdue,
        "completed_week": completed_week,
    }


async def list_team_tasks(
    db: AsyncSession,
    ctx: AgentContext,
    *,
    status: str = "",
    keyword: str = "",
    assignee_user_id: Optional[int] = None,
    priority: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if not _is_admin(ctx) and not ctx.is_supervisor:
        raise TaskError("当前用户不是主管", 403)
    conditions = []
    if not _is_admin(ctx):
        conditions.append(AgentTask.assigner_agent_id == ctx.agent.id)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            conditions.append(AgentTask.status.in_(statuses))
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(or_(
            AgentTask.title.ilike(like),
            AgentTask.task_no.ilike(like),
            AgentTask.biz_no.ilike(like),
        ))
    if assignee_user_id:
        conditions.append(AgentTask.assignee_user_id == int(assignee_user_id))
    if priority:
        conditions.append(AgentTask.priority == priority)
    total = int((await db.execute(
        select(func.count(AgentTask.id)).where(*conditions)
    )).scalar() or 0)
    rows = (await db.execute(
        select(AgentTask)
        .where(*conditions)
        .order_by(AgentTask.status.in_(OPEN_STATUSES).desc(), AgentTask.due_at.asc(), AgentTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()
    names = await display_names(db, rows)
    report_ids = {row.latest_report_id for row in rows if row.latest_report_id}
    reports = {}
    if report_ids:
        report_rows = (await db.execute(
            select(AgentTaskReport.id, AgentTaskReport.summary, AgentTaskReport.version)
            .where(AgentTaskReport.id.in_(sorted(report_ids)))
        )).all()
        reports = {int(row[0]): {"summary": row[1], "version": row[2]} for row in report_rows}
    items = []
    for row in rows:
        data = task_to_dict(
            row,
            assignee_name=names.get(row.assignee_user_id, ""),
            assigner_name=names.get(row.assigner_user_id, ""),
        )
        data["latest_report"] = reports.get(int(row.latest_report_id or 0))
        items.append(data)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def team_task_summary(db: AsyncSession, ctx: AgentContext) -> dict:
    if not _is_admin(ctx) and not ctx.is_supervisor:
        raise TaskError("当前用户不是主管", 403)
    conditions = [] if _is_admin(ctx) else [AgentTask.assigner_agent_id == ctx.agent.id]
    rows = (await db.execute(select(AgentTask).where(*conditions))).scalars().all()
    now = _now()
    week_start = now - timedelta(days=7)
    by_assignee: Dict[int, dict] = {}
    stats = {
        "total": len(rows),
        "open": 0,
        "overdue": 0,
        "blocked": 0,
        "completed_week": 0,
        "analysis_failed": 0,
    }
    for task in rows:
        bucket = by_assignee.setdefault(task.assignee_user_id, {
            "assignee_user_id": task.assignee_user_id,
            "assignee_name": "",
            "open": 0,
            "overdue": 0,
            "blocked": 0,
            "completed_week": 0,
        })
        if task.status in OPEN_STATUSES:
            stats["open"] += 1
            bucket["open"] += 1
        if task.status == "blocked":
            stats["blocked"] += 1
            bucket["blocked"] += 1
        if task.status in OPEN_STATUSES and task.due_at and task.due_at < now:
            stats["overdue"] += 1
            bucket["overdue"] += 1
        if task.status == "completed" and task.completed_at and task.completed_at >= week_start:
            stats["completed_week"] += 1
            bucket["completed_week"] += 1
        if task.analysis_status == "failed":
            stats["analysis_failed"] += 1
    names = await display_names(db, rows)
    for user_id, bucket in by_assignee.items():
        bucket["assignee_name"] = names.get(user_id, "")
    stats["by_assignee"] = sorted(by_assignee.values(), key=lambda item: (-item["open"], item["assignee_user_id"]))
    return stats


async def task_detail(db: AsyncSession, ctx: AgentContext, task_id: int) -> dict:
    task = await _load_task(db, task_id)
    _ensure_participant(ctx, task)
    names = await display_names(db, [task])
    reports = (await db.execute(
        select(AgentTaskReport)
        .where(AgentTaskReport.task_id == task.id)
        .order_by(AgentTaskReport.version.desc())
    )).scalars().all()
    events = (await db.execute(
        select(AgentTaskEvent)
        .where(AgentTaskEvent.task_id == task.id)
        .order_by(AgentTaskEvent.id.asc())
    )).scalars().all()
    data = task_to_dict(
        task,
        assignee_name=names.get(task.assignee_user_id, ""),
        assigner_name=names.get(task.assigner_user_id, ""),
    )
    data.update({
        "analysis_result": task.analysis_result,
        "can_act": int(ctx.user.id) == int(task.assignee_user_id) and task.status in OPEN_STATUSES,
        "can_manage": _is_admin(ctx) or int(ctx.user.id) == int(task.assigner_user_id),
        "reports": [
            {
                "id": report.id,
                "version": report.version,
                "summary": report.summary,
                "result_data": report.result_data,
                "evidence": report.evidence,
                "submitted_by_user_id": report.submitted_by_user_id,
                "submitted_at": _iso(report.submitted_at),
            }
            for report in reports
        ],
        "events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "actor_agent_id": event.actor_agent_id,
                "actor_user_id": event.actor_user_id,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "payload": event.payload,
                "created_at": _iso(event.created_at),
            }
            for event in events
        ],
    })
    return data


async def start_task(db: AsyncSession, ctx: AgentContext, task_id: int) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assignee(ctx, task)
    if task.status != "pending":
        raise TaskError(f"只有待处理任务可以开始，当前状态：{task.status}")
    task.status = "in_progress"
    task.started_at = task.started_at or _now()
    await _add_event(db, task, "started", actor_ctx=ctx, from_status="pending", to_status="in_progress")
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def block_task(db: AsyncSession, ctx: AgentContext, task_id: int, reason: str) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assignee(ctx, task)
    if task.status not in ("pending", "in_progress"):
        raise TaskError(f"只有待处理/处理中任务可以标记阻塞，当前状态：{task.status}")
    reason = (reason or "").strip()
    if not reason:
        raise TaskError("标记阻塞必须填写原因")
    from_status = task.status
    task.status = "blocked"
    await _add_event(
        db, task, "blocked", actor_ctx=ctx, from_status=from_status, to_status="blocked",
        payload={"reason": reason[:2000]},
    )
    assigner = await db.get(SysUser, task.assigner_user_id)
    if assigner:
        await notify_user(
            db,
            user_id=assigner.id,
            title=f"[任务]{ctx.user.display_name or ctx.user.username} 标记任务阻塞",
            content=f"{task.task_no} {task.title}：{reason[:200]}",
            notif_type="agent_task",
            ref_type="agent_task",
            ref_id=task.id,
            ref_no=task.task_no,
            priority="important",
            sender_id=ctx.user.id,
            sender_name=ctx.user.display_name or ctx.user.username,
            wecom_path=task_path(task.id),
            wecom=True,
        )
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def resume_task(db: AsyncSession, ctx: AgentContext, task_id: int) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assignee(ctx, task)
    if task.status != "blocked":
        raise TaskError(f"只有阻塞任务可以恢复，当前状态：{task.status}")
    task.status = "in_progress"
    await _add_event(db, task, "resumed", actor_ctx=ctx, from_status="blocked", to_status="in_progress")
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def submit_report(
    db: AsyncSession,
    ctx: AgentContext,
    task_id: int,
    *,
    summary: str,
    result_data: Optional[dict] = None,
    evidence: Optional[list] = None,
) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assignee(ctx, task)
    if task.status not in OPEN_STATUSES:
        raise TaskError(f"当前状态不能提交汇报：{task.status}")
    summary = (summary or "").strip()
    if not summary:
        raise TaskError("汇报摘要不能为空")
    last_version = int((await db.execute(
        select(func.coalesce(func.max(AgentTaskReport.version), 0))
        .where(AgentTaskReport.task_id == task.id)
    )).scalar() or 0)
    report = AgentTaskReport(
        task_id=task.id,
        version=last_version + 1,
        summary=summary,
        result_data=result_data,
        evidence=evidence,
        submitted_by_agent_id=ctx.agent.id,
        submitted_by_user_id=int(ctx.user.id),
    )
    db.add(report)
    await db.flush()
    from_status = task.status
    task.latest_report_id = report.id
    task.status = "completed"
    task.completed_at = _now()
    await _add_event(
        db, task, "submitted", actor_ctx=ctx, from_status=from_status, to_status="completed",
        payload={"report_id": report.id, "version": report.version, "summary": summary[:500]},
    )
    assigner = await db.get(SysUser, task.assigner_user_id)
    if assigner:
        await notify_user(
            db,
            user_id=assigner.id,
            title=f"[任务]{ctx.user.display_name or ctx.user.username} 提交了任务汇报",
            content=f"{task.task_no} {task.title}：{summary[:200]}",
            notif_type="agent_task",
            ref_type="agent_task",
            ref_id=task.id,
            ref_no=task.task_no,
            sender_id=ctx.user.id,
            sender_name=ctx.user.display_name or ctx.user.username,
            wecom_path=task_path(task.id),
            wecom=True,
        )
    await db.flush()
    await db.refresh(task)
    data = task_to_dict(task)
    data["report"] = {
        "id": report.id,
        "version": report.version,
        "summary": report.summary,
        "submitted_at": _iso(report.submitted_at),
    }
    return data


async def update_task(
    db: AsyncSession,
    ctx: AgentContext,
    task_id: int,
    *,
    due_at=None,
    priority: Optional[str] = None,
) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assigner(ctx, task)
    _ensure_open(task, "改期/改优先级")
    changes = {}
    if due_at is not None:
        new_due = parse_due_at(due_at)
        changes["due_at"] = _iso(new_due)
        task.due_at = new_due
    if priority is not None:
        if priority not in PRIORITIES:
            raise TaskError(f"优先级非法：{priority}")
        changes["priority"] = priority
        task.priority = priority
    if not changes:
        raise TaskError("没有可修改的字段")
    await _add_event(
        db, task, "updated", actor_ctx=ctx, from_status=task.status, to_status=task.status,
        payload={"changes": changes},
    )
    await notify_user(
        db,
        user_id=task.assignee_user_id,
        title="[任务]任务信息已更新",
        content=f"{task.task_no} {task.title}：{'; '.join(f'{k}={v}' for k, v in changes.items())}",
        notif_type="agent_task",
        ref_type="agent_task",
        ref_id=task.id,
        ref_no=task.task_no,
        sender_id=ctx.user.id,
        sender_name=ctx.user.display_name or ctx.user.username,
        wecom_path=task_path(task.id),
        wecom=True,
    )
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def reassign_task(db: AsyncSession, ctx: AgentContext, task_id: int, new_assignee_user_id: int) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assigner(ctx, task)
    if task.status == "completed":
        raise TaskError("已完成任务必须先退回，再改派")
    _ensure_open(task, "改派")
    child = ctx.child_by_user_id(new_assignee_user_id)
    if not child:
        raise TaskError("只能改派给另一个直属子智能体", 403)
    if child.status != "active":
        raise TaskError("目标子智能体已禁用", 400)
    if int(child.user_id) == int(task.assignee_user_id):
        raise TaskError("新接收人与当前接收人相同")
    target_ctx = await load_agent_context(db, await _load_child_user(db, child), use_cache=False)
    if task.task_type == "business":
        try:
            await resolve_business_object(
                db, target_ctx.scope, task.biz_type,
                str(task.biz_id) if task.biz_type == "material_shortage" else (task.biz_no or ""),
                task.biz_context or {},
            )
        except BusinessObjectError as exc:
            raise TaskError(f"新接收人不可见业务对象：{exc.message}", exc.status_code)
    old_user_id = task.assignee_user_id
    old_agent_id = task.assignee_agent_id
    from_status = task.status
    task.assignee_user_id = int(child.user_id)
    task.assignee_agent_id = child.agent_id
    task.status = "pending"
    task.started_at = None
    task.completed_at = None
    task.cancelled_at = None
    task.analysis_status = "pending" if task.task_type == "business" else "skipped"
    task.analysis_result = None
    task.analysis_error = None
    task.analysis_started_at = None
    task.analysis_finished_at = None
    task.analysis_attempts = 0
    await _add_event(
        db, task, "reassigned", actor_ctx=ctx, from_status=from_status, to_status="pending",
        payload={"old_assignee_user_id": old_user_id, "old_assignee_agent_id": old_agent_id,
                 "new_assignee_user_id": child.user_id, "new_assignee_agent_id": child.agent_id},
    )
    await notify_user(
        db,
        user_id=old_user_id,
        title="[任务]任务已改派",
        content=f"{task.task_no} {task.title} 已改派给 {child.display_name}",
        notif_type="agent_task",
        ref_type="agent_task",
        ref_id=task.id,
        ref_no=task.task_no,
        sender_id=ctx.user.id,
        sender_name=ctx.user.display_name or ctx.user.username,
        wecom_path=task_path(task.id),
        wecom=True,
    )
    await notify_user(
        db,
        user_id=child.user_id,
        title=f"[任务]你收到改派任务：{task.title}",
        content=f"{task.task_no}；派发人：{ctx.user.display_name or ctx.user.username}",
        notif_type="agent_task",
        ref_type="agent_task",
        ref_id=task.id,
        ref_no=task.task_no,
        priority="important",
        sender_id=ctx.user.id,
        sender_name=ctx.user.display_name or ctx.user.username,
        wecom_path=task_path(task.id),
        wecom=True,
    )
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def cancel_task(db: AsyncSession, ctx: AgentContext, task_id: int, reason: str) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assigner(ctx, task)
    if task.status == "completed":
        raise TaskError("已完成任务不能取消")
    _ensure_open(task, "取消")
    reason = (reason or "").strip()
    if not reason:
        raise TaskError("取消任务必须填写原因")
    from_status = task.status
    task.status = "cancelled"
    task.cancelled_at = _now()
    await _add_event(
        db, task, "cancelled", actor_ctx=ctx, from_status=from_status, to_status="cancelled",
        payload={"reason": reason[:2000]},
    )
    await notify_user(
        db,
        user_id=task.assignee_user_id,
        title="[任务]任务已取消",
        content=f"{task.task_no} {task.title}：{reason[:200]}",
        notif_type="agent_task",
        ref_type="agent_task",
        ref_id=task.id,
        ref_no=task.task_no,
        sender_id=ctx.user.id,
        sender_name=ctx.user.display_name or ctx.user.username,
        wecom_path=task_path(task.id),
        wecom=True,
    )
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def return_task(db: AsyncSession, ctx: AgentContext, task_id: int, reason: str = "") -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assigner(ctx, task)
    if task.status != "completed":
        raise TaskError(f"只有已完成任务可以退回，当前状态：{task.status}")
    task.status = "in_progress"
    task.completed_at = None
    task.reopen_count = int(task.reopen_count or 0) + 1
    await _add_event(
        db, task, "returned", actor_ctx=ctx, from_status="completed", to_status="in_progress",
        payload={"reason": reason[:2000], "reopen_count": task.reopen_count},
    )
    await notify_user(
        db,
        user_id=task.assignee_user_id,
        title="[任务]任务被退回重做",
        content=f"{task.task_no} {task.title}：{reason[:200] or '请重新处理并提交汇报'}",
        notif_type="agent_task",
        ref_type="agent_task",
        ref_id=task.id,
        ref_no=task.task_no,
        priority="important",
        sender_id=ctx.user.id,
        sender_name=ctx.user.display_name or ctx.user.username,
        wecom_path=task_path(task.id),
        wecom=True,
    )
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def remind_task(db: AsyncSession, ctx: AgentContext, task_id: int) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_assigner(ctx, task)
    _ensure_open(task, "催办")
    key = f"agent_task:remind:{task.id}:manual"
    if not await _redis_set_nx(key, MANUAL_REMIND_TTL_S):
        raise TaskError("2 小时内已催办过，请稍后再试", 429)
    await _add_event(
        db, task, "reminded", actor_ctx=ctx, from_status=task.status, to_status=task.status,
        payload={"by": "manual"},
    )
    await notify_user(
        db,
        user_id=task.assignee_user_id,
        title="[任务]主管催办",
        content=f"{task.task_no} {task.title} 即将到期或已逾期，请尽快处理",
        notif_type="agent_task",
        ref_type="agent_task",
        ref_id=task.id,
        ref_no=task.task_no,
        priority="important",
        sender_id=ctx.user.id,
        sender_name=ctx.user.display_name or ctx.user.username,
        wecom_path=task_path(task.id),
        wecom=True,
    )
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def queue_manual_analysis(db: AsyncSession, ctx: AgentContext, task_id: int) -> dict:
    task = await _load_task(db, task_id, for_update=True)
    _ensure_participant(ctx, task)
    if task.task_type != "business":
        raise TaskError("通用待办无需自动分析")
    if task.status == "cancelled":
        raise TaskError("已取消任务不能重新分析")
    if task.analysis_status == "running":
        raise TaskError("自动分析正在进行中，请稍后再试")
    key = f"agent_task:reanalyze:{task.id}:{int(_now().timestamp() // REANALYZE_KEY_TTL_S)}"
    client = get_command_client()
    if client is not None:
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, REANALYZE_KEY_TTL_S)
            note_success()
            if int(count) > int(get_settings().AGENT_TASK_REANALYZE_LIMIT_PER_HOUR):
                raise TaskError("该任务每小时最多重新分析 3 次，请稍后再试", 429)
        except TaskError:
            raise
        except Exception as exc:
            note_failure()
            logger.warning("[agent-task] 重新分析限流降级 task=%s: %s", task.id, exc)
    task.analysis_status = "pending"
    task.analysis_attempts = 0
    task.analysis_error = None
    await _add_event(
        db, task, "updated", actor_ctx=ctx, from_status=task.status, to_status=task.status,
        payload={"action": "reanalyze"},
    )
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


async def build_task_context(db: AsyncSession, task_id: int, user_id: int) -> str:
    """构造当前任务的系统提示上下文；非参与方拒绝。"""
    task = await _load_task(db, task_id)
    if int(user_id) not in (int(task.assigner_user_id), int(task.assignee_user_id)):
        raise TaskError("无权访问该任务", 403)
    lines = [
        f"任务号：{task.task_no}",
        f"标题：{task.title}",
        f"类型：{task.task_type}",
        f"状态：{task.status}",
        f"截止：{_iso(task.due_at)}",
        f"优先级：{task.priority}",
    ]
    if task.description:
        lines.append(f"要求：{task.description}")
    if task.biz_title:
        lines.append(f"业务对象：{task.biz_title}（{task.biz_type}:{task.biz_no}）")
    if task.biz_context:
        lines.append(f"业务上下文：{task.biz_context}")
    if task.analysis_result:
        lines.append(f"自动分析摘要：{str(task.analysis_result)[:2000]}")
    latest = None
    if task.latest_report_id:
        latest = await db.get(AgentTaskReport, task.latest_report_id)
    if latest:
        lines.append(f"最新汇报（v{latest.version}）：{latest.summary[:1000]}")
    return "\n".join(lines)


async def find_overdue_tasks_for_escalation(db: AsyncSession, hours: int) -> List[AgentTask]:
    threshold = _now() - timedelta(hours=hours)
    return (await db.execute(
        select(AgentTask).where(
            AgentTask.status.in_(OPEN_STATUSES),
            AgentTask.due_at < threshold,
        ).order_by(AgentTask.due_at.asc()).limit(200)
    )).scalars().all()


async def find_due_soon_tasks(db: AsyncSession, hours: int) -> List[AgentTask]:
    now = _now()
    return (await db.execute(
        select(AgentTask).where(
            AgentTask.status.in_(OPEN_STATUSES),
            AgentTask.due_at >= now,
            AgentTask.due_at <= now + timedelta(hours=hours),
        ).order_by(AgentTask.due_at.asc()).limit(500)
    )).scalars().all()
