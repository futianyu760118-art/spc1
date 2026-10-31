"""意图识别单测 — 模型覆盖与推理 token 预算。"""

from app.services.assistant import agent


async def test_recognize_intent_uses_runtime_model_and_reasoning_budget(monkeypatch):
    captured = {}

    async def fake_chat(messages, options):
        captured["options"] = options
        return "QUERY_DATA"

    monkeypatch.setattr(agent.ai_service, "chat", fake_chat)
    intent = await agent._recognize_intent("分析订单风险", [], model_override="deepseek-flash")

    assert intent == "QUERY_DATA"
    assert captured["options"].model == "deepseek-flash"
    assert captured["options"].max_tokens >= 1024
