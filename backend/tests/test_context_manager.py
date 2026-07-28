"""context_manager 单元测试"""

import pytest
from types import SimpleNamespace

from app.services.assistant.context_manager import (
    estimate_tokens,
    estimate_dict_tokens,
    should_summarize,
    build_compressed_messages,
    fallback_sliding_window,
    render_messages_for_summary,
)


def test_estimate_tokens_empty():
    assert estimate_tokens([]) == 0


def test_estimate_tokens_basic():
    msgs = [
        SimpleNamespace(role="system", content="hello world"),
        SimpleNamespace(role="user", content="how are you?"),
    ]
    tokens = estimate_tokens(msgs)
    assert tokens > 0


def test_estimate_dict_tokens_with_tool_calls():
    msgs = [
        {"role": "system", "content": "you are an agent"},
        {"role": "user", "content": "what is X?"},
        {"role": "assistant", "content": "let me search", "tool_calls": [{"function": {"name": "search"}}]},
    ]
    tokens = estimate_dict_tokens(msgs)
    assert tokens > 0


def test_should_summarize_disabled():
    assert should_summarize(100000, 100000, 80000, enabled=False) is False


def test_should_summarize_by_local_tokens():
    assert should_summarize(81000, None, 80000, enabled=True) is True


def test_should_summarize_by_api_tokens():
    assert should_summarize(1000, 90000, 80000, enabled=True) is True


def test_should_summarize_below_threshold():
    assert should_summarize(1000, 1000, 80000, enabled=True) is False


def test_build_compressed_messages_preserves_system_and_users():
    original = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "t1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]
    summaries = {0: "第一轮执行了 search_orders，返回 5 条"}
    result = build_compressed_messages(original, {"role": "system", "content": "sys"}, summaries)
    roles = [m["role"] for m in result]
    assert "system" in roles
    assert "user" in roles
    assert all(m["role"] in ("system", "user") for m in result)


def test_fallback_sliding_window_keeps_system_and_recent():
    original = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
        {"role": "user", "content": "u4"},
    ]
    result = fallback_sliding_window(original, keep_last=4)
    assert result[0]["role"] == "system"
    assert len(result) == 5


def test_render_messages_for_summary_from_chat_message():
    cm = SimpleNamespace(role="user", content="hi", tool_call_id="t1", tool_calls=None)
    rendered = render_messages_for_summary([cm])
    assert rendered[0]["role"] == "user"
    assert rendered[0]["content"] == "hi"
    assert rendered[0]["tool_call_id"] == "t1"


def test_render_messages_for_summary_from_dict():
    rendered = render_messages_for_summary([{"role": "user", "content": "hi"}])
    assert rendered[0]["role"] == "user"
