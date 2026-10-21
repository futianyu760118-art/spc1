"""OpenAI 兼容 Provider 单测 — DeepSeek thinking 模式的 reasoning_content 往返。"""

from types import SimpleNamespace

from app.services.ai.base import ChatMessage, ChatOptions
from app.services.ai.openai_provider import OpenAIProvider


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
