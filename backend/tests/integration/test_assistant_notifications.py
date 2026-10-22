"""AI 助手通知落库契约（测试环境 Redis 不可达，走降级/放行路径）。"""

from sqlalchemy import text

import app.services.notification.assistant_notify as assistant_notify
from app.services.notification.assistant_notify import (
    flush_notifications,
    notify_agent_change,
    notify_agent_gap,
)


async def test_change_notification_rows(db, client):
    notify_agent_change(biz_type="order", biz_no="PO-1", action="update", operator_user_id="1")
    await flush_notifications()
    rows = (
        await db.execute(text(
            "SELECT type, title, ref_type, ref_no FROM notification WHERE ref_no='PO-1'"
        ))
    ).all()
    assert rows
    assert {row[0] for row in rows} == {"assistant_update"}
    assert all(row[2] == "order" for row in rows)
    assert all("更新" in row[1] for row in rows)


async def test_gap_notification_rows(db, client):
    notify_agent_gap(
        biz_type="order", biz_no="PO-2",
        missing_keys=["promised_date"], missing_labels=["合同交期"],
        initiator_user_id="1",
    )
    await flush_notifications()
    rows = (
        await db.execute(text(
            "SELECT type, content FROM notification WHERE ref_no='PO-2'"
        ))
    ).all()
    assert rows
    assert {row[0] for row in rows} == {"assistant_gap"}
    assert all("合同交期" in row[1] for row in rows)


async def test_gap_kill_switch_disables_notice(db, client):
    await db.execute(text("""
        INSERT INTO ai_agent_config (scope, config_key, config_value, value_type)
        VALUES ('assistant', 'gap_notify_enabled', 'false', 'bool')
        ON CONFLICT (scope, config_key) DO UPDATE SET
            config_value=EXCLUDED.config_value, value_type=EXCLUDED.value_type
    """))
    await db.commit()
    try:
        notify_agent_gap(
            biz_type="order", biz_no="PO-3",
            missing_keys=["promised_date"], missing_labels=["合同交期"],
            initiator_user_id="1",
        )
        await flush_notifications()
        count = (
            await db.execute(text("SELECT count(*) FROM notification WHERE ref_no='PO-3'"))
        ).scalar_one()
        assert int(count) == 0
    finally:
        await db.execute(text(
            "DELETE FROM ai_agent_config WHERE scope='assistant' AND config_key='gap_notify_enabled'"
        ))
        await db.commit()


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def eval(self, script, numkeys, *args):
        if "INCR" in script:
            key = args[0]
            count = int(self.store.get(key, 0)) + 1
            self.store[key] = count
            return count
        key, value = args
        if self.store.get(key) == value:
            del self.store[key]
            return 1
        return 0


async def test_gap_dedup_with_redis(db, client, monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(assistant_notify, "get_command_client", lambda: fake)

    async def count_rows() -> int:
        return int((await db.execute(text(
            "SELECT count(*) FROM notification WHERE ref_no='PO-DEDUP'"
        ))).scalar_one())

    notify_agent_gap(
        biz_type="order", biz_no="PO-DEDUP",
        missing_keys=["promised_date"], missing_labels=["合同交期"],
        initiator_user_id="1",
    )
    await flush_notifications()
    first = await count_rows()
    assert first > 0

    notify_agent_gap(
        biz_type="order", biz_no="PO-DEDUP",
        missing_keys=["promised_date"], missing_labels=["合同交期"],
        initiator_user_id="1",
    )
    await flush_notifications()
    assert await count_rows() == first
