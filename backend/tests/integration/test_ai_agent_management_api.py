"""智能体管理台集成测试：配置白名单/版本 bump/统计聚合/agent.config HMAC 拉取"""

import time

from sqlalchemy import text

from tests._common_external import build_headers, generate_signature
from tests.conftest import login


async def test_assistant_config_whitelist_and_version(client):
    headers = await login(client, "admin")

    r = await client.put("/api/v1/system/ai-assistant/config",
                         json={"config": {"hack_key": 1}}, headers=headers)
    assert r.json().get("code") != 0

    r = await client.put("/api/v1/system/ai-assistant/config",
                         json={"config": {"temperature": 0.5, "disabled_tools": ["search_users"]}},
                         headers=headers)
    body = r.json()
    assert body["code"] == 0
    v1 = body["data"]["version"]
    assert v1 >= 1

    r = await client.put("/api/v1/system/ai-assistant/config",
                         json={"config": {"temperature": 0.7}}, headers=headers)
    assert r.json()["data"]["version"] == v1 + 1

    r = await client.get("/api/v1/system/ai-assistant/config", headers=headers)
    config = r.json()["data"]["config"]
    assert config["temperature"] == 0.7
    tools = {t["name"]: t for t in r.json()["data"]["tools"]}
    assert tools["search_users"]["disabled"] is True


async def test_assistant_stats_and_runs(client, db):
    headers = await login(client, "admin")

    await db.execute(text(
        "INSERT INTO assistant_run (trace_id, session_id, user_id, user_message, intent, "
        "tools_called, tool_rounds, total_tokens, duration_ms, is_success, created_at) VALUES "
        "('t1', 's1', 'admin', '查订单', 'agent', '[\"search_orders\"]'::jsonb, 1, 100, 1500.0, TRUE, NOW()), "
        "('t2', 's2', 'admin', '你好', 'general_chat', NULL, 0, 20, 300.0, FALSE, NOW())"
    ))
    await db.commit()

    r = await client.get("/api/v1/system/ai-assistant/stats?days=7", headers=headers)
    data = r.json()["data"]
    assert data["total"] == 2 and data["success"] == 1 and data["total_tokens"] == 120
    assert data["top_tools"][0]["tool"] == "search_orders"

    r = await client.get("/api/v1/system/ai-assistant/runs?days=7", headers=headers)
    assert r.json()["data"]["total"] == 2
    r = await client.get("/api/v1/system/ai-assistant/runs?days=7&is_success=false", headers=headers)
    assert r.json()["data"]["total"] == 1


async def test_execution_agent_config_and_external_fetch(ext_client, client):
    headers = await login(client, "admin")

    r = await client.put("/api/v1/system/execution-agent/config",
                         json={"config": {"query_timeout_ms": 20000, "log_level": "debug"}}, headers=headers)
    assert r.json()["code"] == 0

    key = {"app_key": "ak_pytest_agent", "app_secret": "sk_pytest_agent"}
    ts = int(time.time())
    _, sig = generate_signature(ts, key["app_key"], key["app_secret"], "agent.config", "")
    r = await ext_client.get("/api/v1/external/agent/config",
                             headers=build_headers(key["app_key"], sig, ts))
    data = r.json()["data"]
    assert data["version"] >= 1
    assert data["config"]["query_timeout_ms"] == 20000
    assert data["config"]["log_level"] == "debug"
    # 空值不下发（agent 继续用 env）
    assert "agent_name" not in data["config"]


async def test_execution_agent_status_offline(client):
    headers = await login(client, "admin")
    r = await client.get("/api/v1/system/execution-agent/status", headers=headers)
    assert r.json()["data"]["agent"]["online"] is False
