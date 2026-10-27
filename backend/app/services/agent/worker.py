"""智能体任务 Worker：自动只读分析 + 截止/逾期提醒（随应用启停）。"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.agent.task import AgentTask, AgentTaskEvent
from app.models.basicdata.ai_agent import AssistantRun
from app.models.basicdata.user import SysUser
from app.services.agent.context import load_agent_context
from app.services.agent.notify import notify_user
from app.services.agent.prompt import build_agent_system_prompt
from app.services.agent.task_service import (
    OPEN_STATUSES,
    _add_event,
    _iso,
    _now,
    _redis_set_nx,
    find_due_soon_tasks,
    find_overdue_tasks_for_escalation,
    task_path,
)
from app.services.assistant.orchestrator import resolve_system_prompt, run_reaction

logger = logging.getLogger(__name__)

ANALYSIS_INTERVAL_S = 5
STALE_RUNNING_MINUTES = 10
ANALYSIS_ALLOWED_TOOLS = {"call_query_agent", "call_reasoning_agent", "get_task_detail"}


class AgentTaskWorker:
    def __init__(self):
        self.running = False
        self.tasks: list[asyncio.Task] = []

    def start(self) -> None:
        if not get_settings().AGENT_TASK_ENABLED:
            logger.info("[agent-worker] AGENT_TASK_ENABLED=false，跳过启动")
            return
        if self.running:
            return
        self.running = True
        self.tasks = [
            asyncio.create_task(self._analysis_loop(), name="agent-task-analysis"),
            asyncio.create_task(self._reminder_loop(), name="agent-task-reminder"),
        ]
        logger.info("[agent-worker] 已启动（分析 + 提醒）")

    async def stop(self) -> None:
        self.running = False
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
        logger.info("[agent-worker] 已停止")

    async def _analysis_loop(self) -> None:
        while self.running:
            try:
                await self._recover_stale()
                await self._tick_analysis()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[agent-worker] 分析循环异常: %s", exc)
            await asyncio.sleep(ANALYSIS_INTERVAL_S)

    async def _reminder_loop(self) -> None:
        interval = max(int(get_settings().AGENT_TASK_REMINDER_INTERVAL_SECONDS), 10)
        while self.running:
            try:
                await self._tick_reminders()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[agent-worker] 提醒循环异常: %s", exc)
            await asyncio.sleep(interval)

    async def _recover_stale(self) -> None:
        cutoff = _now() - timedelta(minutes=STALE_RUNNING_MINUTES)
        async with AsyncSessionLocal() as db:
            result = await db.execute(text(
                "UPDATE agent_task SET analysis_status='pending', analysis_started_at=NULL "
                "WHERE analysis_status='running' AND analysis_started_at < :cutoff "
                "AND analysis_attempts < :max_attempts"
            ), {"cutoff": cutoff, "max_attempts": get_settings().AGENT_TASK_ANALYSIS_MAX_ATTEMPTS})
            if result.rowcount:
                logger.warning("[agent-worker] 回收失联分析任务 %s 个", result.rowcount)
            failed = await db.execute(text(
                "UPDATE agent_task SET analysis_status='failed', "
                "analysis_error=COALESCE(analysis_error, '分析进程失联且已达最大重试次数') "
                "WHERE analysis_status='running' AND analysis_started_at < :cutoff "
                "AND analysis_attempts >= :max_attempts"
            ), {"cutoff": cutoff, "max_attempts": get_settings().AGENT_TASK_ANALYSIS_MAX_ATTEMPTS})
            if failed.rowcount:
                logger.warning("[agent-worker] 标记失联分析任务失败 %s 个", failed.rowcount)
            await db.commit()

    async def _claim_batch(self, limit: int) -> list[int]:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(text(
                "SELECT id FROM agent_task WHERE analysis_status='pending' "
                "ORDER BY id ASC LIMIT :lim FOR UPDATE SKIP LOCKED"
            ), {"lim": limit})).all()
            ids = [int(row[0]) for row in rows]
            if ids:
                await db.execute(text(
                    "UPDATE agent_task SET analysis_status='running', "
                    "analysis_started_at=now(), analysis_attempts=analysis_attempts+1, "
                    "analysis_error=NULL WHERE id = ANY(:ids)"
                ), {"ids": ids})
            await db.commit()
            return ids

    async def _tick_analysis(self) -> None:
        concurrency = max(int(get_settings().AGENT_TASK_ANALYSIS_CONCURRENCY), 1)
        task_ids = await self._claim_batch(concurrency)
        if not task_ids:
            return
        await asyncio.gather(*(self._run_analysis(task_id) for task_id in task_ids))

    async def _run_analysis(self, task_id: int) -> None:
        started = _now()
        async with AsyncSessionLocal() as db:
            task = await db.get(AgentTask, task_id)
            if not task or task.analysis_status != "running":
                return
            user = await db.get(SysUser, task.assignee_user_id)
            if not user:
                await self._mark_failed(db, task, "任务接收人不存在", started)
                return
            try:
                await _add_event(
                    db, task, "analysis_started", actor_user_id=user.id,
                    from_status=task.status, to_status=task.status,
                    payload={"attempt": task.analysis_attempts},
                )
                ctx = await load_agent_context(db, user, use_cache=True)
                if ctx.agent.status != "active":
                    raise RuntimeError("智能体已禁用")
                ctx.allowed_tools = set(ANALYSIS_ALLOWED_TOOLS)
                system_prompt = resolve_system_prompt(None, set())
                system_prompt = build_agent_system_prompt(
                    system_prompt, ctx, self._task_context(task),
                )
                prompt = (
                    "请对当前任务做一次只读分析，只使用查询/推理/任务详情工具，不要执行任何写操作。"
                    "输出：1) 现状与关键事实；2) 风险/异常；3) 建议动作；4) 需要用户确认的事项；"
                    "5) 证据与数据时间。若数据不足，明确说明缺少什么。"
                )
                text_parts: list[str] = []
                steps: list = []
                total_tokens = None
                error = None
                timeout = max(int(get_settings().AGENT_TASK_ANALYSIS_TIMEOUT_SECONDS), 5)
                async with asyncio.timeout(timeout):
                    async for event, data in run_reaction(
                        prompt, [],
                        system_prompt=system_prompt,
                        model_override=None,
                        temperature=0.1,
                        max_tokens=4096,
                        max_tool_rounds=4,
                        max_agent_calls=4,
                        disabled_tools=set(),
                        session_id="",
                        trace_id=f"auto-analysis-{task.id}",
                        user_id=str(user.id),
                        provider_name="",
                        stream_final=False,
                        include_order_tool=False,
                        gap_notify=False,
                        db=db,
                        agent_context=ctx,
                        agent_task_id=task.id,
                    ):
                        if event == "delta":
                            text_parts.append(data.get("text") or "")
                        elif event == "done":
                            if not text_parts and data.get("text"):
                                text_parts.append(data["text"])
                            steps = data.get("steps") or []
                            diag = data.get("diagnostics") or {}
                            total_tokens = diag.get("total_tokens")
                            if data.get("failed"):
                                error = "分析流程执行失败"
                        elif event == "error":
                            error = data.get("message") or "分析流程执行失败"
                summary = "".join(text_parts).strip()
                if error or not summary:
                    raise RuntimeError(error or "自动分析未产出内容")

                duration_ms = int((_now() - started).total_seconds() * 1000)
                await db.refresh(task)
                if task.analysis_status != "running":
                    return
                task.analysis_status = "done"
                task.analysis_result = {
                    "summary": summary,
                    "steps": steps,
                    "generated_at": _now().isoformat(),
                    "tokens": total_tokens,
                }
                task.analysis_finished_at = _now()
                task.analysis_error = None
                await _add_event(
                    db, task, "analysis_completed", actor_user_id=user.id,
                    from_status=task.status, to_status=task.status,
                    payload={"tokens": total_tokens, "duration_ms": duration_ms},
                )
                if task.status in OPEN_STATUSES:
                    await notify_user(
                        db,
                        user_id=task.assignee_user_id,
                        title=f"[任务]自动分析已完成：{task.title}",
                        content="已生成现状、风险与建议，请到任务详情查看。",
                        notif_type="agent_analysis",
                        ref_type="agent_task",
                        ref_id=task.id,
                        ref_no=task.task_no,
                    )
                await self._record_run(
                    db, task=task, user=user, status="success",
                    duration_ms=duration_ms, total_tokens=total_tokens,
                )
                await db.commit()
            except asyncio.TimeoutError:
                await self._mark_failed(db, task, "自动分析超时", started)
            except Exception as exc:
                logger.warning("[agent-worker] 任务 %s 分析失败: %s", task_id, exc)
                await self._mark_failed(db, task, str(exc), started)

    def _task_context(self, task: AgentTask) -> str:
        lines = [
            f"任务号：{task.task_no}", f"标题：{task.title}",
            f"类型：{task.task_type}", f"状态：{task.status}",
            f"截止：{_iso(task.due_at)}", f"优先级：{task.priority}",
        ]
        if task.description:
            lines.append(f"要求：{task.description}")
        if task.biz_title:
            lines.append(f"业务对象：{task.biz_title}（{task.biz_type}:{task.biz_no}）")
        if task.biz_context:
            lines.append(f"业务上下文：{json.dumps(task.biz_context, ensure_ascii=False, default=str)}")
        return "\n".join(lines)

    async def _mark_failed(self, db, task: AgentTask, error: str, started: datetime) -> None:
        try:
            await db.refresh(task)
            max_attempts = int(get_settings().AGENT_TASK_ANALYSIS_MAX_ATTEMPTS)
            task.analysis_error = error[:2000]
            task.analysis_finished_at = _now()
            terminal_task = task.status in ("completed", "cancelled")
            if int(task.analysis_attempts or 0) < max_attempts and not terminal_task:
                task.analysis_status = "pending"
                task.analysis_started_at = None
            else:
                task.analysis_status = "failed"
                await _add_event(
                    db, task, "analysis_failed", actor_user_id=task.assignee_user_id,
                    from_status=task.status, to_status=task.status,
                    payload={"error": error[:1000], "attempts": task.analysis_attempts},
                )
                if task.status in OPEN_STATUSES:
                    await notify_user(
                        db,
                        user_id=task.assignee_user_id,
                        title=f"[任务]自动分析失败：{task.title}",
                        content="可到任务详情手动重新分析。",
                        notif_type="agent_analysis",
                        ref_type="agent_task",
                        ref_id=task.id,
                        ref_no=task.task_no,
                    )
            duration_ms = int((_now() - started).total_seconds() * 1000)
            await self._record_run(
                db, task=task, user=None, status="failed",
                duration_ms=duration_ms, total_tokens=None, error=error,
            )
            await db.commit()
        except Exception as exc:
            logger.warning("[agent-worker] 标记分析失败时异常 task=%s: %s", task.id, exc)
            await db.rollback()

    async def _record_run(
        self,
        db,
        *,
        task: AgentTask,
        status: str,
        duration_ms: int,
        total_tokens: Optional[int],
        error: Optional[str] = None,
        tools_called: Optional[list] = None,
    ) -> None:
        db.add(AssistantRun(
            trace_id=f"auto-analysis-{task.id}",
            session_id=None,
            user_id=str(task.assignee_user_id),
            user_message=f"自动分析任务 {task.task_no}"[:500],
            intent="agent",
            agent_id=task.assignee_agent_id,
            task_id=task.id,
            conversation_id=None,
            trigger="auto_analysis",
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            is_success=status == "success",
            error_message=(error or "")[:2000] or None,
        ))

    async def _tick_reminders(self) -> None:
        settings = get_settings()
        async with AsyncSessionLocal() as db:
            due_soon = await find_due_soon_tasks(db, settings.AGENT_TASK_DUE_SOON_HOURS)
            for task in due_soon:
                key = f"agent_task:remind:{task.id}:due_soon:{_iso(task.due_at)}"
                if not await _redis_set_nx(key, 2 * 24 * 3600):
                    continue
                await self._add_reminder_event(db, task, "due_soon")
                await notify_user(
                    db, user_id=task.assignee_user_id,
                    title=f"[任务]即将到期：{task.title}",
                    content=f"{task.task_no} 将于 {task.due_at.strftime('%Y-%m-%d %H:%M')} 到期，请尽快处理。",
                    notif_type="agent_task", ref_type="agent_task", ref_id=task.id,
                    ref_no=task.task_no, priority="important",
                    wecom_path=task_path(task.id), wecom=True,
                )
            await db.commit()

            now = _now()
            overdue = await find_overdue_tasks_for_escalation(db, 0)
            for task in overdue:
                day = now.strftime("%Y%m%d")
                key = f"agent_task:remind:{task.id}:overdue:{day}"
                if await _redis_set_nx(key, 2 * 24 * 3600):
                    await self._add_reminder_event(db, task, "overdue")
                    await notify_user(
                        db, user_id=task.assignee_user_id,
                        title=f"[任务]已逾期：{task.title}",
                        content=f"{task.task_no} 已逾期，截止 {task.due_at.strftime('%Y-%m-%d %H:%M')}，请立即处理。",
                        notif_type="agent_task", ref_type="agent_task", ref_id=task.id,
                        ref_no=task.task_no, priority="urgent",
                        wecom_path=task_path(task.id), wecom=True,
                    )
            await db.commit()

            escalated = await find_overdue_tasks_for_escalation(
                db, settings.AGENT_TASK_OVERDUE_ESCALATION_HOURS,
            )
            for task in escalated:
                day = now.strftime("%Y%m%d")
                key = f"agent_task:remind:{task.id}:overdue_escalation:{day}"
                if not await _redis_set_nx(key, 2 * 24 * 3600):
                    continue
                await self._add_reminder_event(db, task, "overdue_escalation")
                await notify_user(
                    db, user_id=task.assigner_user_id,
                    title=f"[任务]下属任务逾期超过 {settings.AGENT_TASK_OVERDUE_ESCALATION_HOURS} 小时",
                    content=f"{task.task_no} {task.title} 已逾期，接收人未完成。",
                    notif_type="agent_task", ref_type="agent_task", ref_id=task.id,
                    ref_no=task.task_no, priority="urgent",
                    wecom_path=task_path(task.id), wecom=True,
                )
            await db.commit()

    async def _add_reminder_event(self, db, task: AgentTask, kind: str) -> None:
        db.add(AgentTaskEvent(
            task_id=task.id,
            event_type="reminded",
            actor_user_id=None,
            from_status=task.status,
            to_status=task.status,
            payload={"by": kind},
        ))


agent_task_worker = AgentTaskWorker()
