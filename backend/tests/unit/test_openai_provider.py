"""OpenAI 兼容 Provider 单测 — DeepSeek thinking 模式的 reasoning_content 往返。"""

from types import SimpleNamespace

import pytest

from app.services.ai import openai_provider
from app.services.ai.base import ChatMessage, ChatOptions
from app.services.ai.openai_provider import OpenAIProvider


@pytest.fixture(autouse=True)
def _fake_openai_sdk(monkeypatch):
    """不依赖本机安装 openai 包：用 FakeClient 覆盖 SDK 客户端。"""
    monkeypatch.setattr(openai_provider, "_HAS_OPENAI", True)
    monkeypatch.setattr(openai_provider, "AsyncOpenAI", lambda **kwargs: None, raising=False)


class _FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.response


class _FakeClient:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)
        self.chat = SimpleNamespace(completions=self.completions)


def _provider(response):
    provider = OpenAIProvider(api_key="test", model="deepseek-flash", base_url="http://localhost")
    provider._client = _FakeClient(response)
    return provider


def _tool_messages():
    return [
        ChatMessage(role="system", content="sys"),
        ChatMessage(role="user", content="查订单"),
        ChatMessage(
            role="assistant",
            content="",
            reasoning_content="先调用查询智能体",
            tool_calls=[{
                "id": "call-1",
                "type": "function",
                "function": {"name": "call_query_agent", "arguments": "{}"},
            }],
        ),
        ChatMessage(role="tool", content="{\"items\": []}", tool_call_id="call-1"),
    ]


async def test_chat_with_tools_round_trips_reasoning_content():
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(
                content=None,
                reasoning_content="需要查订单",
                tool_calls=[SimpleNamespace(
                    id="call-2",
                    function=SimpleNamespace(name="call_query_agent", arguments='{"path": "/x"}'),
                )],
            ),
            finish_reason="tool_calls",
        )],
        usage=None,
    )
    provider = _provider(response)

    result = await provider.chat_with_tools(_tool_messages(), [], ChatOptions(temperature=0.1, max_tokens=256))

    sent = provider._client.completions.requests[0]["messages"]
    assert sent[2]["reasoning_content"] == "先调用查询智能体"
    assert sent[2]["tool_calls"][0]["id"] == "call-1"
    assert sent[3]["tool_call_id"] == "call-1"
    assert result.thinking == "需要查订单"
    assert result.tool_calls[0].name == "call_query_agent"


async def test_chat_keeps_tool_history_fields():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="总结", reasoning_content=None), finish_reason="stop")],
        usage=None,
    )
    provider = _provider(response)

    text = await provider.chat(_tool_messages(), ChatOptions(temperature=0.1, max_tokens=256))

    sent = provider._client.completions.requests[0]["messages"]
    assert text == "总结"
    assert sent[2]["reasoning_content"] == "先调用查询智能体"
    assert sent[2]["tool_calls"][0]["id"] == "call-1"
    assert sent[3]["tool_call_id"] == "call-1"


async def test_chat_passes_per_request_timeout():
    """推理 170s 依赖按请求透传 timeout，不能被 AI_REQUEST_TIMEOUT 提前截断。"""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", reasoning_content=None), finish_reason="stop")],
        usage=None,
    )
    provider = _provider(response)

    await provider.chat(_tool_messages(), ChatOptions(timeout=170))

    assert provider._client.completions.requests[0]["timeout"] == 170


async def test_chat_with_tools_parses_deepseek_dsml_content():
    content = """<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="install_skill">
<｜｜DSML｜｜ parameter name="skill_key" string="true">@zcwl/multi-search-engine</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>"""
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, reasoning_content=None, tool_calls=None),
            finish_reason="stop",
        )],
        usage=None,
    )
    provider = _provider(response)

    result = await provider.chat_with_tools(_tool_messages(), [], ChatOptions())

    assert result.text in (None, "")
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "install_skill"
    assert result.tool_calls[0].arguments == {"skill_key": "@zcwl/multi-search-engine"}

async def test_chat_with_tools_parses_xml_tool_call_content():
    content = """<tool_call>
{"name": "install_skill", "arguments": {"skill": "@zcwl/multi-search-engine"}}
</tool_call>"""
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, reasoning_content=None, tool_calls=None),
            finish_reason="stop",
        )],
        usage=None,
    )
    provider = _provider(response)

    result = await provider.chat_with_tools(_tool_messages(), [], ChatOptions())

    assert result.text in (None, "")
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "install_skill"
    assert result.tool_calls[0].arguments == {"skill": "@zcwl/multi-search-engine"}
