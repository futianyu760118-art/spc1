"""写操作确认单单测 — 创建 / 读取 / 原子消费（内存降级路径）"""

from app.services.assistant import write_confirmation
from app.services.assistant.write_confirmation import (
    CONFIRMATION_TTL_S,
    create_confirmation,
    get_confirmation,
    consume_confirmation,
)


async def test_create_assigns_id_and_expiry(monkeypatch):
    monkeypatch.setattr(write_confirmation, "get_command_client", lambda: None)
    write_confirmation._memory_store.clear()
    record = await create_confirmation({"order_no": "HJ-1", "fields": {"shipping_plan": "2026-11-01"}})
    assert record["confirmation_id"].startswith("wc-")
    assert record["expires_at"] and record["created_at"]
    assert record["ttl_s"] == CONFIRMATION_TTL_S


async def test_consume_once_then_missing(monkeypatch):
    monkeypatch.setattr(write_confirmation, "get_command_client", lambda: None)
    write_confirmation._memory_store.clear()
    record = await create_confirmation({"order_no": "HJ-1"})
    cid = record["confirmation_id"]

    got = await get_confirmation(cid)
    assert got is not None and got["order_no"] == "HJ-1"

    consumed = await consume_confirmation(cid)
    assert consumed is not None and consumed["confirmation_id"] == cid

    assert await get_confirmation(cid) is None
    assert await consume_confirmation(cid) is None


async def test_consume_redis_script_atomic(monkeypatch):
    """Redis 路径：消费走 Lua GET+DEL，同一 key 只返回一次。"""
    store = {}

    class FakeRedis:
        async def setex(self, key, ttl, value):
            store[key] = value

        async def get(self, key):
            return store.get(key)

        async def eval(self, script, numkeys, *keys):
            key = keys[0]
            value = store.get(key)
            if value is not None:
                store.pop(key, None)
            return value

    fake = FakeRedis()
    monkeypatch.setattr(write_confirmation, "get_command_client", lambda: fake)
    monkeypatch.setattr(write_confirmation, "note_success", lambda: None)
    monkeypatch.setattr(write_confirmation, "note_failure", lambda: None)
    write_confirmation._memory_store.clear()

    record = await create_confirmation({"order_no": "HJ-2"})
    first = await consume_confirmation(record["confirmation_id"])
    second = await consume_confirmation(record["confirmation_id"])
    assert first is not None
    assert second is None


async def test_missing_confirmation_returns_none(monkeypatch):
    monkeypatch.setattr(write_confirmation, "get_command_client", lambda: None)
    write_confirmation._memory_store.clear()
    assert await get_confirmation("wc-nope") is None
    assert await consume_confirmation("wc-nope") is None
