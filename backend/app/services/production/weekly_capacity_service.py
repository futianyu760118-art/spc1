"""下周产能计划查询与企业微信推送。

数据来源为当前生效的月度排产方案（monthly_schedule_plan.is_active），
按自然周（周一到周日）汇总为 H5 只读页面所需的日明细。
"""
from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.basicdata.employee import Employee
from app.models.basicdata.organization import Organization
from app.models.basicdata.position import Position
from app.models.basicdata.share_link import ShareLink
from app.models.basicdata.user import SysRole, SysUser
from app.models.production.monthly_schedule_plan import MonthlySchedulePlan
from app.models.production.weekly_capacity import WeeklyPlanSnapshot, WeeklyPushRecipient
from app.services.basicdata.wecom.client import get_wecom_client

logger = logging.getLogger(__name__)

STAGE_LABELS = {"assembly": "组装", "packaging": "包装"}
WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
SHARE_EXPIRES_DAYS = 30
WEEKLY_SHARE_PATH = "/weekly-share.html"


def resolve_next_week_range(today: Optional[date] = None) -> tuple[date, date]:
    """返回下一个自然周的周一、周日。"""
    current = today or date.today()
    start = current + timedelta(days=7 - current.weekday())
    return start, start + timedelta(days=6)


def _row_hours(row: MonthlySchedulePlan) -> float:
    quantity = float(row.quantity or 0)
    upph = float(row.upph or 0)
    manpower = int(row.manpower or 0)
    if quantity <= 0 or upph <= 0 or manpower <= 0:
        return 0.0
    return round(quantity / (upph * manpower), 2)


def _serialize_week_row(
    row: MonthlySchedulePlan,
    *,
    status: str,
    continued_from_prev_week: bool,
) -> dict[str, Any]:
    return {
        "order_no": row.order_no,
        "line_no": row.line_no,
        "product_code": row.product_code,
        "product_name": row.product_name,
        "bom_no": row.bom_no,
        "stage": row.schedule_bucket,
        "stage_label": STAGE_LABELS.get(row.schedule_bucket, row.schedule_bucket),
        "quantity": round(float(row.quantity or 0)),
        "manpower": int(row.manpower or 0),
        "daily_work_hours": float(row.daily_work_hours or 0),
        "hours": _row_hours(row),
        "status": status,
        "remark": row.remark or "",
        "continued_from_prev_week": continued_from_prev_week,
    }


def _day_status(load_hours: float, capacity_hours: float) -> str:
    if capacity_hours <= 0:
        return "ok"
    rate = load_hours / capacity_hours
    if rate > 1.2:
        return "risk"
    if rate > 1.0:
        return "warn"
    return "ok"


async def build_weekly_capacity(
    db: AsyncSession,
    *,
    week_start: Optional[date] = None,
) -> dict[str, Any]:
    start, end = (
        (week_start, week_start + timedelta(days=6))
        if week_start
        else resolve_next_week_range()
    )
    rows = (
        await db.execute(
            select(MonthlySchedulePlan)
            .where(
                MonthlySchedulePlan.is_active == True,  # noqa: E712
                MonthlySchedulePlan.plan_date >= start,
                MonthlySchedulePlan.plan_date <= end,
                MonthlySchedulePlan.schedule_bucket.in_(tuple(STAGE_LABELS)),
            )
            .order_by(MonthlySchedulePlan.plan_date.asc(), MonthlySchedulePlan.id.asc())
        )
    ).scalars().all()

    first_dates = (
        await db.execute(
            select(
                MonthlySchedulePlan.order_no,
                MonthlySchedulePlan.line_no,
                MonthlySchedulePlan.schedule_bucket,
                func.min(MonthlySchedulePlan.plan_date),
            )
            .where(MonthlySchedulePlan.is_active == True)  # noqa: E712
            .group_by(
                MonthlySchedulePlan.order_no,
                MonthlySchedulePlan.line_no,
                MonthlySchedulePlan.schedule_bucket,
            )
        )
    ).all()
    first_date_map = {
        (str(order_no), str(line_no), str(bucket)): first_date
        for order_no, line_no, bucket, first_date in first_dates
    }

    rows_by_date: dict[date, list[MonthlySchedulePlan]] = {}
    for row in rows:
        rows_by_date.setdefault(row.plan_date, []).append(row)

    days: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for offset in range(7):
        current_date = start + timedelta(days=offset)
        day_rows = rows_by_date.get(current_date, [])
        stage_hours = {stage: 0.0 for stage in STAGE_LABELS}
        stage_capacity = {stage: 0.0 for stage in STAGE_LABELS}
        for row in day_rows:
            stage = str(row.schedule_bucket)
            if stage not in stage_hours:
                continue
            stage_hours[stage] += _row_hours(row)
            stage_capacity[stage] = max(
                stage_capacity[stage],
                float(row.manpower or 0) * float(row.daily_work_hours or 0),
            )
        stage_status = {
            stage: _day_status(stage_hours[stage], stage_capacity[stage])
            for stage in STAGE_LABELS
        }
        serialized_rows = [
            _serialize_week_row(
                row,
                status=stage_status.get(str(row.schedule_bucket), "ok"),
                continued_from_prev_week=(
                    first_date_map.get(
                        (str(row.order_no), str(row.line_no), str(row.schedule_bucket))
                    ) or current_date
                ) < start,
            )
            for row in day_rows
        ]
        all_rows.extend(serialized_rows)
        days.append({
            "date": current_date.isoformat(),
            "weekday": WEEKDAY_LABELS[offset],
            "order_count": len({row["order_no"] for row in serialized_rows}),
            "line_count": len(serialized_rows),
            "total_qty": sum(row["quantity"] for row in serialized_rows),
            "stage_hours": {
                stage: round(hours, 2) for stage, hours in stage_hours.items()
            },
            "rows": serialized_rows,
        })

    stage_hours_total = {
        stage: round(sum(row["hours"] for row in all_rows if row["stage"] == stage), 2)
        for stage in STAGE_LABELS
    }
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "has_plan": bool(all_rows),
        "summary": {
            "order_count": len({row["order_no"] for row in all_rows}),
            "line_count": len(all_rows),
            "total_qty": sum(row["quantity"] for row in all_rows),
            "stage_hours": stage_hours_total,
        },
        "days": days,
    }


def _frontend_base() -> str:
    settings = get_settings()
    base = settings.frontend_base_url or "http://localhost:3000"
    if base and not base.startswith(("http://", "https://")):
        base = "http://" + base
    return base.rstrip("/")


def _serialize_snapshot(snapshot: WeeklyPlanSnapshot) -> dict[str, Any]:
    data = dict(snapshot.detail_json or {})
    data.update({
        "snapshot_id": snapshot.id,
        "snapshot_no": snapshot.snapshot_no,
        "snapshot_status": snapshot.status,
        "published_at": snapshot.published_at.isoformat() if snapshot.published_at else None,
    })
    return data


async def list_weekly_recipients(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(WeeklyPushRecipient, SysUser)
            .join(SysUser, WeeklyPushRecipient.user_id == SysUser.id)
            .order_by(WeeklyPushRecipient.category.asc(), WeeklyPushRecipient.id.asc())
        )
    ).all()
    return [
        {
            "id": recipient.id,
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "category": recipient.category,
            "enabled": bool(recipient.enabled),
            "wecom_user_id": user.wecom_user_id,
            "remark": recipient.remark,
        }
        for recipient, user in rows
    ]


async def list_weekly_recipient_options(db: AsyncSession) -> dict[str, Any]:
    orgs = (
        await db.execute(
            select(Organization.id, Organization.org_name, Organization.parent_id)
            .where(Organization.status == 1)
            .order_by(Organization.parent_id.asc().nullsfirst(), Organization.id.asc())
        )
    ).all()
    roles = (
        await db.execute(
            select(SysRole.role_code, SysRole.role_name)
            .where(SysRole.role_code != "supplier")
            .order_by(SysRole.role_name.asc())
        )
    ).all()
    return {
        "orgs": [
            {"id": int(org_id), "name": org_name, "parent_id": int(parent_id) if parent_id else None}
            for org_id, org_name, parent_id in orgs
        ],
        "roles": [
            {"value": role_code, "label": role_name}
            for role_code, role_name in roles
        ],
    }


async def list_weekly_recipient_candidates(
    db: AsyncSession,
    *,
    keyword: Optional[str] = None,
    org_id: Optional[int] = None,
    role_code: Optional[str] = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    query = (
        select(SysUser, SysRole, Employee, Position, Organization)
        .join(SysRole, SysUser.role_id == SysRole.id)
        .outerjoin(Employee, SysUser.scm_employee_id == Employee.id)
        .outerjoin(Position, Employee.position_id == Position.id)
        .outerjoin(Organization, cast(Employee.org_id, String) == Organization.oa_org_id)
        .where(
            SysUser.is_active == True,  # noqa: E712
            SysRole.role_code != "supplier",
        )
    )
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                SysUser.username.ilike(like),
                SysUser.display_name.ilike(like),
                Employee.emp_name.ilike(like),
            )
        )
    if org_id is not None:
        query = query.where(Organization.id == org_id)
    if role_code:
        query = query.where(SysRole.role_code == role_code)

    rows = (
        await db.execute(
            query.order_by(
                Organization.org_name.asc().nulls_last(),
                SysUser.display_name.asc().nulls_last(),
                SysUser.id.asc(),
            ).limit(limit)
        )
    ).all()
    recipient_rows = (await db.execute(select(WeeklyPushRecipient))).scalars().all()
    recipient_map = {row.user_id: row for row in recipient_rows}
    return [
        {
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name or (employee.emp_name if employee else None) or user.username,
            "role_code": role.role_code,
            "role_name": role.role_name,
            "org_id": int(org.id) if org else None,
            "org_name": org.org_name if org else None,
            "position_name": position.position_name if position else None,
            "wecom_user_id": user.wecom_user_id,
            "is_recipient": user.id in recipient_map,
            "enabled": bool(recipient_map[user.id].enabled) if user.id in recipient_map else False,
        }
        for user, role, employee, position, org in rows
    ]


async def update_weekly_recipients(
    db: AsyncSession,
    *,
    items: list[dict[str, Any]],
    operator: str | None = None,
) -> list[dict[str, Any]]:
    for item in items:
        recipient = None
        if item.get("id"):
            recipient = await db.get(WeeklyPushRecipient, int(item["id"]))
        if recipient is None and item.get("user_id"):
            recipient = (
                await db.execute(
                    select(WeeklyPushRecipient).where(
                        WeeklyPushRecipient.user_id == int(item["user_id"])
                    )
                )
            ).scalar_one_or_none()
        if recipient is None and item.get("user_id"):
            user = await db.get(SysUser, int(item["user_id"]))
            if user and user.is_active:
                recipient = WeeklyPushRecipient(
                    user_id=user.id,
                    category=str(item.get("category") or "").strip() or None,
                    enabled=bool(item.get("enabled", True)),
                    created_by=operator,
                )
                db.add(recipient)
        if recipient is None:
            continue
        if "enabled" in item:
            recipient.enabled = bool(item["enabled"])
        if item.get("category"):
            recipient.category = str(item["category"]).strip() or None
        if item.get("remark") is not None:
            recipient.remark = str(item["remark"]).strip() or None
        if operator:
            recipient.created_by = recipient.created_by or operator
        db.add(recipient)
    await db.flush()
    return await list_weekly_recipients(db)


async def generate_weekly_snapshot(
    db: AsyncSession,
    *,
    week_start: Optional[date] = None,
    operator: str | None = None,
) -> dict[str, Any]:
    data = await build_weekly_capacity(db, week_start=week_start)
    if not data["has_plan"]:
        raise ValueError("下周暂无排产计划，请先生成并激活下周计划")

    start = date.fromisoformat(data["week_start"])
    count = (
        await db.execute(
            select(func.count()).select_from(WeeklyPlanSnapshot).where(
                WeeklyPlanSnapshot.week_start == start
            )
        )
    ).scalar() or 0
    snapshot_no = f"WP{datetime.now():%Y%m%d}-{count + 1:03d}"
    snapshot = WeeklyPlanSnapshot(
        snapshot_no=snapshot_no,
        week_start=start,
        week_end=date.fromisoformat(data["week_end"]),
        schedule_month=start.strftime("%Y-%m"),
        summary_json=data["summary"],
        detail_json=data,
        status="draft",
        generated_by=operator,
    )
    db.add(snapshot)
    await db.flush()
    logger.info("[下周排产] 生成快照 %s %s~%s", snapshot_no, data["week_start"], data["week_end"])
    return _serialize_snapshot(snapshot)


async def list_weekly_snapshots(
    db: AsyncSession,
    *,
    week_start: Optional[date] = None,
) -> list[dict[str, Any]]:
    query = select(WeeklyPlanSnapshot).order_by(
        WeeklyPlanSnapshot.generated_at.desc(),
        WeeklyPlanSnapshot.id.desc(),
    )
    if week_start:
        query = query.where(WeeklyPlanSnapshot.week_start == week_start)
    rows = (await db.execute(query.limit(100))).scalars().all()
    return [
        {
            "id": row.id,
            "snapshot_no": row.snapshot_no,
            "week_start": row.week_start.isoformat(),
            "week_end": row.week_end.isoformat(),
            "status": row.status,
            "generated_at": row.generated_at.isoformat() if row.generated_at else None,
            "published_at": row.published_at.isoformat() if row.published_at else None,
        }
        for row in rows
    ]


async def get_weekly_snapshot(db: AsyncSession, snapshot_id: int) -> dict[str, Any]:
    snapshot = await db.get(WeeklyPlanSnapshot, snapshot_id)
    if not snapshot:
        raise ValueError("周计划快照不存在")
    return _serialize_snapshot(snapshot)


async def get_latest_published_snapshot(db: AsyncSession) -> dict[str, Any] | None:
    snapshot = (
        await db.execute(
            select(WeeklyPlanSnapshot)
            .where(WeeklyPlanSnapshot.status == "published")
            .order_by(WeeklyPlanSnapshot.week_start.desc(), WeeklyPlanSnapshot.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _serialize_snapshot(snapshot) if snapshot else None


async def _resolve_recipients(db: AsyncSession) -> list[SysUser]:
    result = await db.execute(
        select(SysUser)
        .join(WeeklyPushRecipient, WeeklyPushRecipient.user_id == SysUser.id)
        .where(
            WeeklyPushRecipient.enabled == True,  # noqa: E712
            SysUser.is_active == True,  # noqa: E712
            SysUser.wecom_user_id.isnot(None),
            SysUser.wecom_user_id != "",
        )
        .order_by(WeeklyPushRecipient.id.asc())
    )
    return list(result.scalars().all())


async def publish_weekly_snapshot(
    db: AsyncSession,
    *,
    snapshot_id: int,
    operator_id: int,
) -> dict[str, Any]:
    snapshot = await db.get(WeeklyPlanSnapshot, snapshot_id)
    if not snapshot:
        raise ValueError("周计划快照不存在")
    data = dict(snapshot.detail_json or {})
    if not data.get("has_plan"):
        raise ValueError("该快照没有排产计划，不能推送")

    recipients = await _resolve_recipients(db)
    if not recipients:
        raise ValueError("没有启用的企业微信收件人，请先配置推送名单")

    token = secrets.token_urlsafe(24)
    share = ShareLink(
        token=token,
        target_path=WEEKLY_SHARE_PATH,
        target_params={"token": token, "snapshot_id": snapshot.id},
        permissions=["read"],
        reason="下周排产计划推送",
        created_by=operator_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=SHARE_EXPIRES_DAYS),
    )
    db.add(share)
    await db.flush()

    share_url = f"{_frontend_base()}/share/{token}"
    summary = data.get("summary") or {}
    stage_hours = summary.get("stage_hours") or {}
    title = f"下周排产计划 {data.get('week_start', '')[5:]} ~ {data.get('week_end', '')[5:]}"
    description = (
        f"订单 {summary.get('order_count', 0)} 个 / 明细 {summary.get('line_count', 0)} 行 / "
        f"数量 {summary.get('total_qty', 0)} 件\n"
        f"组装 {float(stage_hours.get('assembly', 0)):.1f} 人时 / "
        f"包装 {float(stage_hours.get('packaging', 0)):.1f} 人时"
    )
    textcard = {
        "title": title,
        "description": description,
        "url": share_url,
        "btntxt": "查看下周计划",
    }

    client = get_wecom_client()
    agent_id = int(client._settings.wecom_agent_id or 0)
    payload = {
        "touser": "|".join([user.wecom_user_id for user in recipients]),
        "msgtype": "textcard",
        "agentid": agent_id,
        "textcard": textcard,
    }
    result = {
        "snapshot_id": snapshot.id,
        "snapshot_no": snapshot.snapshot_no,
        "week_start": data.get("week_start"),
        "week_end": data.get("week_end"),
        "share_url": share_url,
        "recipients": [user.display_name or user.username for user in recipients],
        "summary": summary,
        "success": False,
        "failed": [],
    }
    try:
        resp = await client.send_app_message(payload)
        errcode = resp.get("errcode", 0)
        if errcode != 0:
            error_msg = f"errcode={errcode} {resp.get('errmsg', '')}"
            logger.error("[下周排产] 企业微信推送失败: %s", error_msg)
            result["failed"] = [
                {"recipient_id": user.wecom_user_id, "name": user.display_name or user.username, "error_msg": error_msg}
                for user in recipients
            ]
            result["error"] = error_msg
            return result
    except Exception as exc:
        logger.exception("[下周排产] 企业微信推送异常: %s", exc)
        result["failed"] = [
            {"recipient_id": user.wecom_user_id, "name": user.display_name or user.username, "error_msg": str(exc)}
            for user in recipients
        ]
        result["error"] = f"企业微信推送失败: {exc}"
        return result

    await db.execute(
        update(WeeklyPlanSnapshot)
        .where(
            WeeklyPlanSnapshot.week_start == snapshot.week_start,
            WeeklyPlanSnapshot.id != snapshot.id,
            WeeklyPlanSnapshot.status == "published",
        )
        .values(status="superseded")
    )
    snapshot.status = "published"
    snapshot.published_at = datetime.now()
    snapshot.share_link_id = share.id
    await db.flush()
    result["success"] = True
    result["published_at"] = snapshot.published_at.isoformat()
    logger.info(
        "[下周排产] 推送成功 -> %s %s~%s",
        [user.username for user in recipients],
        data.get("week_start"),
        data.get("week_end"),
    )
    return result


async def push_weekly_capacity(
    db: AsyncSession,
    *,
    operator_id: int,
) -> dict[str, Any]:
    """兼容旧入口：生成快照后立即推送。"""
    snapshot = await generate_weekly_snapshot(db, operator=str(operator_id))
    return await publish_weekly_snapshot(
        db,
        snapshot_id=int(snapshot["snapshot_id"]),
        operator_id=operator_id,
    )
