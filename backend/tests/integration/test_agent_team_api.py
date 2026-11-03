"""智能体团队 API 集成测试：目录 CRUD、开放范围、勾选/移除与 effective 能力收敛。

错误响应经 _err/_capture 包裹（HTTP 200 + code!=0）；真实 403 仅来自权限依赖。
"""

from tests.conftest import get_user_id_by_username, login

ADMIN_AGENTS = "/api/v1/agents/admin/agents"
ADMIN_USERS = "/api/v1/agents/admin/users"
ADMIN_BIND = "/api/v1/agents/admin/users/bind"
TEAM = "/api/v1/agents/me/team"
ME = "/api/v1/agents/me"
UNASSIGNED_ROLE_ID = 999999


def _payload(name, capabilities=("query.orders",), **kw):
    return {"name": name, "capabilities": list(capabilities), **kw}


async def _create_agent(client, headers, name, **kw):
    r = await client.post(ADMIN_AGENTS, json=_payload(name, **kw), headers=headers)
    body = r.json()
    assert body["code"] == 0, r.text
    return body["data"]


async def test_admin_crud_duplicate_and_unknown_capability(client):
    headers = await login(client, "admin")

    created = await _create_agent(client, headers, "订单查询员A")
    assert created["agent_no"].startswith("AG-")
    assert created["scope_type"] == "all"
    assert created["status"] == "active"
    assert [c["code"] for c in created["capabilities"]] == ["query.orders"]

    r = await client.get(ADMIN_AGENTS, headers=headers)
    body = r.json()
    assert body["code"] == 0, r.text
    assert created["id"] in [item["id"] for item in body["data"]["items"]]

    r = await client.post(ADMIN_AGENTS, json=_payload("订单查询员A"), headers=headers)
    assert r.json()["code"] == 400
    assert "同名" in r.json()["message"]

    r = await client.post(
        ADMIN_AGENTS, json=_payload("神秘员", capabilities=["query.nonsense"]), headers=headers)
    assert r.json()["code"] == 400
    assert "未知能力" in r.json()["message"]

    r = await client.post(
        ADMIN_AGENTS, json=_payload("空白能力员", capabilities=[]), headers=headers)
    assert r.json()["code"] == 400
    assert "至少选择一个能力" in r.json()["message"]

    r = await client.put(
        f"{ADMIN_AGENTS}/{created['id']}",
        json=_payload("订单查询员A2", capabilities=("query.orders", "query.order_details")),
        headers=headers)
    assert r.json()["code"] == 0, r.text
    assert r.json()["data"]["name"] == "订单查询员A2"
    assert {c["code"] for c in r.json()["data"]["capabilities"]} == {"query.orders", "query.order_details"}


async def test_scope_roles_hidden_from_candidates(client):
    headers = await login(client, "admin")
    roles_agent = await _create_agent(
        client, headers, "限定角色查询员",
        scope_type="roles", scope_role_ids=[UNASSIGNED_ROLE_ID],
    )
    all_agent = await _create_agent(client, headers, "全员查询员")

    user_headers = await login(client, "qa_mgr")
    r = await client.get(f"{TEAM}/candidates", headers=user_headers)
    body = r.json()
    assert body["code"] == 0, r.text
    ids = {item["id"] for item in body["data"]["items"]}
    assert all_agent["id"] in ids
    assert roles_agent["id"] not in ids


async def test_team_check_duplicate_forbidden_and_remove(client):
    admin_headers = await login(client, "admin")
    agent = await _create_agent(client, admin_headers, "勾选测试员")
    hidden_agent = await _create_agent(
        client, admin_headers, "限权勾选员",
        scope_type="roles", scope_role_ids=[UNASSIGNED_ROLE_ID],
    )

    headers = await login(client, "qa_mgr")
    r = await client.post(TEAM, json={"agent_id": agent["id"]}, headers=headers)
    assert r.json()["code"] == 0, r.text

    r = await client.get(TEAM, headers=headers)
    body = r.json()
    assert body["code"] == 0, r.text
    assert any(item["id"] == agent["id"] for item in body["data"]["items"])

    r = await client.post(TEAM, json={"agent_id": agent["id"]}, headers=headers)
    assert r.json()["code"] == 400
    assert "已在你的团队中" in r.json()["message"]

    r = await client.post(TEAM, json={"agent_id": hidden_agent["id"]}, headers=headers)
    assert r.json()["code"] == 403
    assert "未对你开放" in r.json()["message"]

    r = await client.delete(f"{TEAM}/{agent['id']}", headers=headers)
    assert r.json()["code"] == 0, r.text

    r = await client.post(TEAM, json={"agent_id": agent["id"]}, headers=headers)
    assert r.json()["code"] == 0, r.text


async def test_me_effective_capabilities_follow_team(client):
    admin_headers = await login(client, "admin")
    agent = await _create_agent(
        client, admin_headers, "效果测试查询员",
        capabilities=("query.orders", "query.order_details"),
    )

    headers = await login(client, "qa_fin")
    r = await client.get(ME, headers=headers)
    body = r.json()
    assert body["code"] == 0, r.text
    codes = {c["code"] for c in body["data"]["effective_capabilities"]}
    assert "query.orders" not in codes

    r = await client.post(TEAM, json={"agent_id": agent["id"]}, headers=headers)
    assert r.json()["code"] == 0, r.text
    r = await client.get(ME, headers=headers)
    codes = {c["code"] for c in r.json()["data"]["effective_capabilities"]}
    assert {"query.orders", "query.order_details"} <= codes

    r = await client.delete(f"{TEAM}/{agent['id']}", headers=headers)
    assert r.json()["code"] == 0, r.text
    r = await client.get(ME, headers=headers)
    codes = {c["code"] for c in r.json()["data"]["effective_capabilities"]}
    assert codes == set()


async def test_disabled_member_capability_converges(client):
    admin_headers = await login(client, "admin")
    agent = await _create_agent(client, admin_headers, "停用测试查询员")

    headers = await login(client, "qa_gm")
    r = await client.post(TEAM, json={"agent_id": agent["id"]}, headers=headers)
    assert r.json()["code"] == 0, r.text
    r = await client.get(ME, headers=headers)
    codes = {c["code"] for c in r.json()["data"]["effective_capabilities"]}
    assert "query.orders" in codes

    r = await client.put(
        f"{ADMIN_AGENTS}/{agent['id']}",
        json=_payload("停用测试查询员", status="disabled"), headers=admin_headers)
    assert r.json()["code"] == 0, r.text

    r = await client.get(ME, headers=headers)
    codes = {c["code"] for c in r.json()["data"]["effective_capabilities"]}
    assert "query.orders" not in codes


async def test_admin_batch_bind_and_unbind_users(client):
    admin_headers = await login(client, "admin")
    agent_a = await _create_agent(client, admin_headers, "batch-bind-a")
    agent_b = await _create_agent(client, admin_headers, "batch-bind-b")
    user_a = await get_user_id_by_username("qa_mgr")
    user_b = await get_user_id_by_username("qa_gm")

    r = await client.get(ADMIN_USERS, headers=admin_headers)
    assert r.json()["code"] == 0
    user_ids = {item["id"] for item in r.json()["data"]["items"]}
    assert {user_a, user_b} <= user_ids

    r = await client.post(ADMIN_BIND, json={
        "agent_ids": [agent_a["id"], agent_b["id"]],
        "user_ids": [user_a, user_b],
        "action": "bind",
    }, headers=admin_headers)
    body = r.json()
    assert body["code"] == 0, r.text
    assert body["data"]["created"] == 4

    headers_a = await login(client, "qa_mgr")
    r = await client.get(TEAM, headers=headers_a)
    team_ids = {item["id"] for item in r.json()["data"]["items"]}
    assert {agent_a["id"], agent_b["id"]} <= team_ids

    r = await client.post(ADMIN_BIND, json={
        "agent_ids": [agent_a["id"]],
        "user_ids": [user_a],
        "action": "bind",
    }, headers=admin_headers)
    assert r.json()["data"]["created"] == 0
    assert r.json()["data"]["skipped"] == 1

    r = await client.post(ADMIN_BIND, json={
        "agent_ids": [agent_a["id"], agent_b["id"]],
        "user_ids": [user_a, user_b],
        "action": "unbind",
    }, headers=admin_headers)
    assert r.json()["code"] == 0, r.text
    assert r.json()["data"]["removed"] == 4

    r = await client.get(TEAM, headers=headers_a)
    team_ids = {item["id"] for item in r.json()["data"]["items"]}
    assert agent_a["id"] not in team_ids


async def test_admin_bind_respects_agent_scope(client):
    admin_headers = await login(client, "admin")
    agent = await _create_agent(
        client, admin_headers, "scope-bind",
        scope_type="roles", scope_role_ids=[UNASSIGNED_ROLE_ID],
    )
    user_id = await get_user_id_by_username("qa_mgr")
    r = await client.post(ADMIN_BIND, json={
        "agent_ids": [agent["id"]],
        "user_ids": [user_id],
        "action": "bind",
    }, headers=admin_headers)
    body = r.json()
    assert body["code"] == 0, r.text
    assert body["data"]["created"] == 0
    assert body["data"]["skipped"] == 1
    assert body["data"]["skipped_details"]
