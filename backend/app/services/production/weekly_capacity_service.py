"""下周产能计划查询与企业微信推送。

数据来源为当前生效的月度排产方案（monthly_schedule_plan.is_active），
按自然周（周一到周日）汇总为 H5 只读页面所需的日明细。
"""
from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.basicdata.share_link import ShareLink
from app.models.basicdata.user import SysUser
from app.models.production.monthly_schedule_plan import MonthlySchedulePlan
from app.services.basicdata.wecom.client import get_wecom_client

logger = logging.getLogger(__name__)

STAGE_LABELS = {"assembly": "组装", "packaging": "包装"}
WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
# 测试阶段只推送陈巧霞；全量 13 人名单见 docs/下周排产计划推送-计划书.md
TEST_RECIPIENT_USERNAMES = ("chenqiaoxia",)
SHARE_EXPIRES_DAYS = 30
WEEKLY_CAPACITY_PATH = "/weekly-capacity"


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


async def _resolve_recipients(
    db: AsyncSession,
    usernames: tuple[str, ...],
) -> list[SysUser]:
    if not usernames:
        return []
    result = await db.execute(
        select(SysUser).where(
            SysUser.username.in_(usernames),
            SysUser.is_active == True,  # noqa: E712
            SysUser.wecom_user_id.isnot(None),
            SysUser.wecom_user_id != "",
        )
    )
    return list(result.scalars().all())


def _frontend_base() -> str:
    settings = get_settings()
    base = settings.frontend_base_url or "http://localhost:3000"
    if base and not base.startswith(("http://", "https://")):
        base = "http://" + base
    return base.rstrip("/")


async def push_weekly_capacity(
    db: AsyncSession,
    *,
    operator_id: int,
) -> dict[str, Any]:
    data = await build_weekly_capacity(db)
    if not data["has_plan"]:
        raise ValueError("下周暂无排产计划，请先生成并激活下周计划")

    recipients = await _resolve_recipients(db, TEST_RECIPIENT_USERNAMES)
    if not recipients:
        raise ValueError("未找到已绑定企业微信的测试收件人（陈巧霞）")

    token = secrets.token_urlsafe(24)
    share = ShareLink(
        token=token,
        target_path=WEEKLY_CAPACITY_PATH,
        target_params={"week_start": data["week_start"]},
        permissions=["read"],
        reason="下周产能计划推送",
        created_by=operator_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=SHARE_EXPIRES_DAYS),
    )
    db.add(share)
    await db.flush()

    share_url = f"{_frontend_base()}/share/{token}"
    summary = data["summary"]
    stage_hours = summary["stage_hours"]
    title = f"下周产能计划 {data['week_start'][5:]} ~ {data['week_end'][5:]}"
    description = (
        f"订单 {summary['order_count']} 个 / 明细 {summary['line_count']} 行 / "
        f"数量 {summary['total_qty']} 件\n"
        f"组装 {stage_hours.get('assembly', 0):.1f} 人时 / "
        f"包装 {stage_hours.get('packaging', 0):.1f} 人时"
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
        "week_start": data["week_start"],
        "week_end": data["week_end"],
        "share_url": share_url,
        "recipients": [user.display_name or user.username for user in recipients],
        "summary": summary,
    }
    try:
        resp = await client.send_app_message(payload)
    except Exception as exc:  # 企微未配置/接口异常不应吞掉已生成的分享链接
        logger.exception("[下周产能] 企业微信推送异常: %s", exc)
        return {**result, "success": False, "error": f"企业微信推送失败: {exc}"}

    errcode = resp.get("errcode", 0)
    if errcode != 0:
        error_msg = f"errcode={errcode} {resp.get('errmsg', '')}"
        logger.error("[下周产能] 企业微信推送失败: %s", error_msg)
        return {**result, "success": False, "error": f"企业微信推送失败: {error_msg}"}

    logger.info(
        "[下周产能] 推送成功 -> %s %s~%s",
        [user.username for user in recipients],
        data["week_start"],
        data["week_end"],
    )
    return {**result, "success": True}
