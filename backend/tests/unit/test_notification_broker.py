"""通知 SSE broker 断线重连与 degraded/recovered 事件测试。

不起 Redis/DB：_snapshot 与 make_pubsub_client 以桩替换，逐帧消费
subscribe_stream 输出，断言「断链→degraded→重连补偿快照→recovered」事件序列。
"""

import asyncio
import json

from app.services.notification import notification_broker as broker


class _FakePubSub:
    def __init__(self, messages=None, fail_times=0):
        self._messages = list(messages or [])
        self._fail_times = fail_times
        self.channel = None
        self.closed = False

    async def subscribe(self, channel):
        self.channel = channel

    async def get_message(self, ignore_subscribe_messages=True, timeout=None):
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ConnectionError("Connection closed by server.")
        if self._messages:
            return {"type": "message", "data": json.dumps(self._messages.pop(0))}
        return None

    async def aclose(self):
        self.closed = True


class _FakeClient:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        self.closed = True


def _stub_snapshot(monkeypatch, totals: list[int]) -> None:
    queue = list(totals)

    async def fake_snapshot(user_id):
        return {"total": queue.pop(0), "by_type": {}}

    monkeypatch.setattr(broker, "_snapshot", fake_snapshot)


def _stub_clients(monkeypatch, clients: list) -> None:
    def factory():
        item = clients.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(broker, "make_pubsub_client", factory)


def _event(frame: str) -> str:
    return frame.splitlines()[0].removeprefix("event: ")


def _payload(frame: str) -> dict:
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line[6:])


def _is_last_unread(total: int):
    def predicate(frames: list[str]) -> bool:
        return _event(frames[-1]) == "unread" and _payload(frames[-1])["total"] == total

    return predicate


async def _frames_until(gen, predicate, timeout: float = 3.0) -> list[str]:
    frames: list[str] = []

    async def _run():
        async for frame in gen:
            frames.append(frame)
            if predicate(frames):
                break

    try:
        await asyncio.wait_for(_run(), timeout)
    finally:
        await gen.aclose()
    return frames


async def test_subscribe_failure_degrades_then_recovers(monkeypatch):
    """首次订阅失败：先发 degraded，重连成功后补快照并解除降级。"""
    _stub_snapshot(monkeypatch, [1, 2])
    _stub_clients(monkeypatch, [
        ConnectionError("redis down"),
        _FakeClient(_FakePubSub(messages=[{"total": 3, "by_type": {}}])),
    ])
    monkeypatch.setattr(broker, "RECONNECT_BACKOFF_SEC", (0, 0))

    frames = await _frames_until(broker.subscribe_stream(7), _is_last_unread(3))

    assert [_event(f) for f in frames] == ["unread", "degraded", "unread", "recovered", "unread"]
    assert [_payload(f)["total"] for f in frames if _event(f) == "unread"] == [1, 2, 3]


async def test_pubsub_drop_reconnects_with_compensation_snapshot(monkeypatch):
    """流中途断链：释放旧连接、发 degraded，重连后补偿快照 + recovered。"""
    _stub_snapshot(monkeypatch, [1, 2, 3])
    dropped_pubsub = _FakePubSub(fail_times=1)
    dropped_client = _FakeClient(dropped_pubsub)
    _stub_clients(monkeypatch, [
        dropped_client,
        _FakeClient(_FakePubSub(messages=[{"total": 9, "by_type": {}}])),
    ])
    monkeypatch.setattr(broker, "RECONNECT_BACKOFF_SEC", (0, 0))

    frames = await _frames_until(broker.subscribe_stream(7), _is_last_unread(9))

    assert [_event(f) for f in frames] == [
        "unread", "unread", "degraded", "unread", "recovered", "unread",
    ]
    assert dropped_pubsub.closed and dropped_client.closed


async def test_publish_unread_updates_degrades_without_redis(db):
    from app.services.notification.notification_broker import publish_unread_updates
    await publish_unread_updates(db, [1, 2, 3])
