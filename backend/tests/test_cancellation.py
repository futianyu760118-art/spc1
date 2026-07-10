"""cancellation 单元测试"""

import asyncio

import pytest

from app.services.assistant.cancellation import CancellationRegistry


@pytest.mark.asyncio
async def test_get_or_create_returns_event():
    ev = await CancellationRegistry.get_or_create("sess-1")
    assert isinstance(ev, asyncio.Event)
    assert not ev.is_set()
    CancellationRegistry.cleanup("sess-1")


@pytest.mark.asyncio
async def test_trigger_marks_cancelled():
    await CancellationRegistry.get_or_create("sess-2")
    assert CancellationRegistry.is_cancelled("sess-2") is False

    CancellationRegistry.trigger("sess-2", "client_disconnected")
    assert CancellationRegistry.is_cancelled("sess-2") is True
    assert CancellationRegistry.reason("sess-2") == "client_disconnected"
    CancellationRegistry.cleanup("sess-2")


@pytest.mark.asyncio
async def test_cleanup_removes_session():
    await CancellationRegistry.get_or_create("sess-3")
    assert CancellationRegistry.get_sync("sess-3") is not None

    CancellationRegistry.cleanup("sess-3")
    assert CancellationRegistry.get_sync("sess-3") is None
    assert CancellationRegistry.is_cancelled("sess-3") is False


@pytest.mark.asyncio
async def test_trigger_unknown_session_is_safe():
    CancellationRegistry.trigger("nonexistent", "noop")
    assert CancellationRegistry.is_cancelled("nonexistent") is False


def test_clear_all():
    CancellationRegistry.clear_all()
    assert CancellationRegistry.get_sync("anything") is None
