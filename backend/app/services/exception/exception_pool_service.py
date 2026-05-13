"""异常与质量中心 — 异常总池聚合 + 闭环跟踪服务"""

from datetime import date
from collections import defaultdict
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exception.risk_issue import RiskIssue
from app.models.exception.issue_log import IssueLog
from app.models.exception.change_log import ChangeLog
from app.models.exception.quality_issue import QualityIssue
from app.models.production.process_exception import ProcessException
from app.schemas.exception.schemas import (
    ExceptionPoolItem,
    ClosureTrackingData,
    ClosureStatusCount,
    ClosureByTypeItem,
    ClosureByPersonItem,
)


async def get_exception_pool(
    db: AsyncSession,
    source_type: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ExceptionPoolItem], int]:
    """聚合查询所有异常源，返回统一分页结果"""
    items: list[ExceptionPoolItem] = []
    today = date.today()

    # --- RiskIssue ---
    if not source_type or source_type == "risk_issue":
        q = select(RiskIssue)
        if status:
            q = q.where(RiskIssue.status == status)
        if owner:
            q = q.where(RiskIssue.owner.ilike(f'%{owner}%'))
        if keyword:
            like = f'%{keyword}%'
            q = q.where(
                RiskIssue.description.ilike(like)
                | RiskIssue.issue_no.ilike(like)
                | RiskIssue.order_no.ilike(like)
            )
        result = await db.execute(q.order_by(RiskIssue.created_at.desc()))
        for r in result.scalars().all():
            items.append(ExceptionPoolItem(
                source_type="risk_issue",
                source_id=r.id,
                source_no=r.issue_no,
                title=r.description,
                status=r.status,
                severity=r.risk_level,
                owner=r.owner,
                order_no=r.order_no,
                created_at=r.created_at,
            ))

    # --- QualityIssue ---
    if not source_type or source_type == "quality_issue":
        q = select(QualityIssue)
        if status:
            q = q.where(QualityIssue.status == status)
        if owner:
            q = q.where(QualityIssue.responsible_person.ilike(f'%{owner}%'))
        if keyword:
            like = f'%{keyword}%'
            q = q.where(
                QualityIssue.description.ilike(like)
                | QualityIssue.issue_no.ilike(like)
                | QualityIssue.order_no.ilike(like)
            )
        result = await db.execute(q.order_by(QualityIssue.created_at.desc()))
        for r in result.scalars().all():
            items.append(ExceptionPoolItem(
                source_type="quality_issue",
                source_id=r.id,
                source_no=r.issue_no,
                title=r.description,
                status=r.status,
                severity=None,
                owner=r.responsible_person,
                order_no=r.order_no,
                created_at=r.created_at,
            ))

    # --- ProcessException ---
    if not source_type or source_type == "process_exception":
        q = select(ProcessException)
        if status:
            q = q.where(ProcessException.status == status)
        if owner:
            q = q.where(ProcessException.responsible_person.ilike(f'%{owner}%'))
        if keyword:
            like = f'%{keyword}%'
            q = q.where(
                ProcessException.description.ilike(like)
                | ProcessException.exception_no.ilike(like)
                | ProcessException.order_no.ilike(like)
            )
        result = await db.execute(q.order_by(ProcessException.created_at.desc()))
        for r in result.scalars().all():
            items.append(ExceptionPoolItem(
                source_type="process_exception",
                source_id=r.id,
                source_no=r.exception_no,
                title=r.description,
                status=r.status,
                severity=r.severity,
                owner=r.responsible_person,
                order_no=r.order_no,
                created_at=r.created_at,
            ))

    # --- IssueLog (read-only, always show) ---
    if not source_type or source_type == "issue_log":
        q = select(IssueLog)
        if keyword:
            like = f'%{keyword}%'
            q = q.where(IssueLog.description.ilike(like))
        result = await db.execute(q.order_by(IssueLog.created_at.desc()))
        for r in result.scalars().all():
            items.append(ExceptionPoolItem(
                source_type="issue_log",
                source_id=r.id,
                source_no=f"IL-{r.seq_no or r.id:04d}",
                title=r.description,
                status='open',  # IssueLog has no status field
                severity=None,
                owner=r.recorder,
                order_no=None,
                created_at=r.created_at,
            ))

    # --- ChangeLog (read-only, always show) ---
    if not source_type or source_type == "change_log":
        q = select(ChangeLog)
        if keyword:
            like = f'%{keyword}%'
            q = q.where(ChangeLog.change_content.ilike(like))
        result = await db.execute(q.order_by(ChangeLog.created_at.desc()))
        for r in result.scalars().all():
            items.append(ExceptionPoolItem(
                source_type="change_log",
                source_id=r.id,
                source_no=f"CL-{r.seq_no or r.id:04d}",
                title=r.change_content,
                status='open',  # ChangeLog has no status field
                severity=None,
                owner=r.modifier,
                order_no=None,
                created_at=r.created_at,
            ))

    # Sort all items by created_at desc
    items.sort(key=lambda x: x.created_at or date.min, reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    return page_items, total


async def get_closure_tracking(db: AsyncSession) -> ClosureTrackingData:
    """闭环跟踪统计：跨所有异常源统计状态分布、超时数、按类型/责任人分布"""
    today = date.today()
    status_counts: dict[str, int] = defaultdict(int)
    by_type: dict[str, dict] = defaultdict(lambda: {"open": 0, "in_progress": 0, "closed": 0, "overdue": 0})
    by_person: dict[str, dict] = defaultdict(lambda: {"open": 0, "in_progress": 0, "closed": 0, "overdue": 0})

    # --- RiskIssue ---
    result = await db.execute(select(RiskIssue))
    for r in result.scalars().all():
        s = r.status
        status_counts[s] += 1
        by_type["risk_issue"][s] = by_type["risk_issue"].get(s, 0) + 1
        overdue = s != "closed" and r.commit_date and r.commit_date < today
        if overdue:
            by_type["risk_issue"]["overdue"] = by_type["risk_issue"].get("overdue", 0) + 1
        owner = r.owner or "未分配"
        by_person[owner][s] = by_person[owner].get(s, 0) + 1
        if overdue:
            by_person[owner]["overdue"] = by_person[owner].get("overdue", 0) + 1

    # --- QualityIssue ---
    result = await db.execute(select(QualityIssue))
    for r in result.scalars().all():
        s = r.status
        status_counts[s] += 1
        by_type["quality_issue"][s] = by_type["quality_issue"].get(s, 0) + 1
        overdue = s != "closed" and r.submit_date and r.submit_date < today
        if overdue:
            by_type["quality_issue"]["overdue"] = by_type["quality_issue"].get("overdue", 0) + 1
        owner = r.responsible_person or "未分配"
        by_person[owner][s] = by_person[owner].get(s, 0) + 1
        if overdue:
            by_person[owner]["overdue"] = by_person[owner].get("overdue", 0) + 1

    # --- ProcessException ---
    result = await db.execute(select(ProcessException))
    for r in result.scalars().all():
        s = r.status
        status_counts[s] += 1
        by_type["process_exception"][s] = by_type["process_exception"].get(s, 0) + 1
        overdue = s != "closed" and r.resolved_at is None
        if overdue:
            by_type["process_exception"]["overdue"] = by_type["process_exception"].get("overdue", 0) + 1
        owner = r.responsible_person or "未分配"
        by_person[owner][s] = by_person[owner].get(s, 0) + 1
        if overdue:
            by_person[owner]["overdue"] = by_person[owner].get("overdue", 0) + 1

    # Build result
    sc_list = [ClosureStatusCount(status=s, count=c) for s, c in sorted(status_counts.items())]
    bt_list = [
        ClosureByTypeItem(
            source_type=st,
            open_count=d.get("open", 0),
            in_progress_count=d.get("in_progress", 0),
            closed_count=d.get("closed", 0),
            overdue_count=d.get("overdue", 0),
        )
        for st, d in sorted(by_type.items())
    ]
    bp_list = [
        ClosureByPersonItem(
            owner=p,
            open_count=d.get("open", 0),
            in_progress_count=d.get("in_progress", 0),
            closed_count=d.get("closed", 0),
            overdue_count=d.get("overdue", 0),
        )
        for p, d in sorted(by_person.items())
    ]

    return ClosureTrackingData(
        status_counts=sc_list,
        by_type=bt_list,
        by_person=bp_list,
        total_open=status_counts.get("open", 0),
        total_in_progress=status_counts.get("in_progress", 0),
        total_closed=status_counts.get("closed", 0),
        total_overdue=sum(d.get("overdue", 0) for d in by_type.values()),
    )
