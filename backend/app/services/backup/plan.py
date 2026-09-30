"""备份管理纯逻辑（无 IO）：保留策略 / 定时窗口 / 强确认 / 连接串解析"""

from datetime import datetime, timedelta

CONFIRM_TEXT = "确认恢复"


def parse_schedule_time(schedule_time: str) -> tuple[int, int]:
    """'HH:MM' -> (hour, minute)，非法值回落 03:30"""
    try:
        parts = schedule_time.split(":")
        hh, mm = int(parts[0]), int(parts[1])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except (ValueError, IndexError):
        pass
    return 3, 30


def _candidate_at(now: datetime, schedule_time: str) -> datetime:
    hh, mm = parse_schedule_time(schedule_time)
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


def compute_next_run(*, frequency: str, schedule_time: str, weekday: int | None, now: datetime) -> datetime:
    """now 之后（严格大于）的下一次触发时间（naive 本地时间）"""
    candidate = _candidate_at(now, schedule_time)
    step_days = 1
    if frequency == "weekly":
        target_wd = (weekday or 1) - 1  # python: Monday=0
        candidate -= timedelta(days=(candidate.weekday() - target_wd) % 7)
        step_days = 7
    if candidate <= now:
        candidate += timedelta(days=step_days)
    return candidate


def last_due_time(*, frequency: str, schedule_time: str, weekday: int | None, now: datetime) -> datetime:
    """最近一个已到达（<= now）的触发时间点，用于判断是否错过窗口"""
    candidate = _candidate_at(now, schedule_time)
    step_days = 1
    if frequency == "weekly":
        target_wd = (weekday or 1) - 1
        candidate -= timedelta(days=(candidate.weekday() - target_wd) % 7)
        step_days = 7
    if candidate > now:
        candidate -= timedelta(days=step_days)
    return candidate


def select_outdated_records(records: list[dict], retention_count: int) -> list[int]:
    """从按 created_at 降序的记录中选出应删除的 id。

    保留最新 retention_count 份；无论 retention_count 多小，最新一份（records[0]）永不删除。
    """
    keep = max(1, retention_count or 1)
    return [r["id"] for r in records[keep:]]


def confirm_matches(text: str | None) -> bool:
    return (text or "").strip() == CONFIRM_TEXT


def pg_target_from_url(database_url: str) -> dict:
    """解析 DATABASE_URL 为 pg_dump/pg_restore 连接参数（密码仅经环境变量传递）"""
    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    return {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "database": url.database or "",
        "user": url.username or "",
        "password": url.password or "",
    }
