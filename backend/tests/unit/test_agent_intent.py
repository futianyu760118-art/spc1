import pytest

from app.services.assistant import agent
from app.services.assistant.agent import _is_search_request, _is_skill_management_request


def test_skill_management_requests_route_to_task():
    assert _is_skill_management_request(
        "请根据 https://skillhub.cn/install/skillhub.md，安装 @zcwl/multi-search-engine。"
    )
    assert _is_skill_management_request("帮我卸载技能 tech-test-automation")
    assert _is_skill_management_request("安装 @zcwl/multi-search-engine")
    assert _is_skill_management_request("使用技能生成一份文档")


def test_general_chat_is_not_skill_management():
    assert not _is_skill_management_request("你好")
    assert not _is_skill_management_request("查询订单 HJ202604-0018-0086")

@pytest.mark.asyncio
async def test_skill_intent_short_circuits_llm(monkeypatch):
    async def _unexpected(*args, **kwargs):
        raise AssertionError("skill management must not use the general-chat intent path")

    monkeypatch.setattr(agent, "_intent_chat_with_retry", _unexpected)

    intent = await agent._recognize_intent(
        "请根据 https://skillhub.cn/install/skillhub.md 安装 @zcwl/multi-search-engine。",
        [], None, None,
    )

    assert intent == "QUERY_DATA"

def test_search_requests_route_to_task():
    assert _is_search_request("搜最近国产大模型发布消息、多找几个来源")
    assert _is_search_request("帮我查一下最新的新闻")
    assert not _is_search_request("你好")


@pytest.mark.asyncio
async def test_search_intent_short_circuits_llm(monkeypatch):
    async def _unexpected(*args, **kwargs):
        raise AssertionError("search requests must enter the tool-capable orchestrator")

    monkeypatch.setattr(agent, "_intent_chat_with_retry", _unexpected)

    intent = await agent._recognize_intent("搜最近国产大模型发布消息、多找几个来源", [], None, None)

    assert intent == "QUERY_DATA"
