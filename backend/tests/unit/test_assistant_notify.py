"""通知注册表与调度入口的纯逻辑测试。"""

from app.services.notification import assistant_notify as notify


async def test_valid_change_schedules(monkeypatch):
    scheduled = []
    monkeypatch.setattr(notify, "_schedule", lambda coro: scheduled.append(coro))
    notify.notify_agent_change(biz_type="order", biz_no="PO1", action="update", operator_user_id="1")
    assert len(scheduled) == 1
    scheduled[0].close()


async def test_flush_waits_for_scheduled_task():
    done = []

    async def work():
        done.append(True)

    notify._schedule(work())
    await notify.flush_notifications()
    assert done == [True]


async def test_unknown_action_skips(monkeypatch):
    scheduled = []
    monkeypatch.setattr(notify, "_schedule", lambda coro: scheduled.append(coro))
    notify.notify_agent_change(biz_type="order", biz_no="PO1", action="approve", operator_user_id="1")
    assert scheduled == []


async def test_no_biz_no_skips(monkeypatch):
    scheduled = []
    monkeypatch.setattr(notify, "_schedule", lambda coro: scheduled.append(coro))
    notify.notify_agent_change(biz_type="order", biz_no="", action="update", operator_user_id="1")
    assert scheduled == []


async def test_gap_key_stable_and_field_key_based():
    a = notify._gap_key("order", "PO1", ["promised_date", "shipping_plan"])
    b = notify._gap_key("order", "PO1", ["shipping_plan", "promised_date"])
    c = notify._gap_key("order", "PO1", ["promised_date"])
    assert a == b != c


async def test_action_types_cover_three_actions():
    assert notify.ACTION_CONFIG["update"]["type"] == "assistant_update"
    assert notify.ACTION_CONFIG["create"]["type"] == "assistant_create"
    assert notify.ACTION_CONFIG["delete"]["type"] == "assistant_delete"


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


async def test_gap_rate_limit_with_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(notify, "get_command_client", lambda: fake)
    results = [
        await notify._allow_gap_event("1")
        for _ in range(notify.GAP_RATE_LIMIT_PER_HOUR + 1)
    ]
    assert results[: notify.GAP_RATE_LIMIT_PER_HOUR] == [True] * notify.GAP_RATE_LIMIT_PER_HOUR
    assert results[-1] is False


async def test_claim_slot_dedup_and_compare_release(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(notify, "get_command_client", lambda: fake)
    assert await notify.claim_slot("k", "batch-1") is True
    assert await notify.claim_slot("k", "batch-2") is False
    await notify.release_slot("k", "batch-2")
    assert await notify.claim_slot("k", "batch-3") is False
    await notify.release_slot("k", "batch-1")
    assert await notify.claim_slot("k", "batch-4") is True
