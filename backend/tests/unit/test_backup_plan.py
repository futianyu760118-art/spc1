"""备份管理纯逻辑单测（无 IO、无事件循环）"""

from datetime import datetime

from app.services.backup.plan import (
    confirm_matches,
    compute_next_run,
    last_due_time,
    parse_schedule_time,
    pg_target_from_url,
    select_outdated_records,
)


def test_retention_keeps_latest_n_and_never_newest():
    records = [{"id": i} for i in range(10)]  # 已按 created_at 降序
    assert select_outdated_records(records, 7) == [7, 8, 9]
    assert select_outdated_records(records, 10) == []
    assert select_outdated_records(records, 1) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    # retention 非法值永不删除最新一份
    assert select_outdated_records(records, 0)[0] == 1
    assert 0 not in select_outdated_records(records, 0)


def test_next_run_daily_and_weekly():
    # daily：今天 10:00，定时 03:30 → 明天 03:30
    assert compute_next_run(frequency="daily", schedule_time="03:30", weekday=None,
                            now=datetime(2026, 9, 29, 10, 0)) == datetime(2026, 9, 30, 3, 30)
    # daily：今天 02:00，定时 03:30 → 今天 03:30
    assert compute_next_run(frequency="daily", schedule_time="03:30", weekday=None,
                            now=datetime(2026, 9, 29, 2, 0)) == datetime(2026, 9, 29, 3, 30)
    # weekly：2026-09-29 是周二，weekday=3（周三）→ 下一个周三是明天 09-30
    assert compute_next_run(frequency="weekly", schedule_time="03:30", weekday=3,
                            now=datetime(2026, 9, 29, 10, 0)) == datetime(2026, 9, 30, 3, 30)


def test_last_due_time():
    # 周二 10:00，weekly weekday=3（周三）→ 上周三 03:30
    assert last_due_time(frequency="weekly", schedule_time="03:30", weekday=3,
                         now=datetime(2026, 9, 29, 10, 0)) == datetime(2026, 9, 23, 3, 30)
    # 周二 02:00，weekly weekday=3（周三）→ 仍是上周三 03:30（本周三 09-30 尚未到）
    assert last_due_time(frequency="weekly", schedule_time="03:30", weekday=3,
                         now=datetime(2026, 9, 29, 2, 0)) == datetime(2026, 9, 23, 3, 30)
    # daily：10:00 → 今天 03:30
    assert last_due_time(frequency="daily", schedule_time="03:30", weekday=None,
                         now=datetime(2026, 9, 29, 10, 0)) == datetime(2026, 9, 29, 3, 30)


def test_parse_schedule_time_fallback():
    assert parse_schedule_time("03:30") == (3, 30)
    assert parse_schedule_time("23:59") == (23, 59)
    assert parse_schedule_time("bad") == (3, 30)
    assert parse_schedule_time("25:00") == (3, 30)


def test_confirm_matches():
    assert confirm_matches("确认恢复") is True
    assert confirm_matches("  确认恢复 ") is True
    assert confirm_matches("确认") is False
    assert confirm_matches(None) is False


def test_pg_target_from_url():
    target = pg_target_from_url("postgresql+asyncpg://user:secret@dbhost:5433/spc_db")
    assert target == {"host": "dbhost", "port": 5433, "database": "spc_db",
                      "user": "user", "password": "secret"}
