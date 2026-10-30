"""resolve-caller 内网端点：token 鉴权、USER_NOT_FOUND 拒绝、agentId 元数据审计。"""

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.agent.gateway import GatewayDispatchLog
from tests.conftest import seed_query_agent_for_user


async def test_requires_gateway_token(client):
    settings = get_settings()
    saved = settings.GATEWAY_INTERNAL_TOKEN
    settings.GATEWAY_INTERNAL_TOKEN = "test-gateway-token"
    try:
        r = await client.post("/api/v1/internal/gateway/resolve-caller", json={
            "runId": "r1", "capability": "query_control_platform", "input": {},
        })
        assert r.status_code == 401
    finally:
        settings.GATEWAY_INTERNAL_TOKEN = saved


async def test_rejects_unknown_user_with_audit(client):
    settings = get_settings()
    saved = settings.GATEWAY_INTERNAL_TOKEN
    settings.GATEWAY_INTERNAL_TOKEN = "test-gateway-token"
    try:
        r = await client.post(
            "/api/v1/internal/gateway/resolve-caller",
            headers={"X-Gateway-Token": "test-gateway-token"},
            json={
                "runId": "r2", "capability": "query_control_platform", "input": {},
                "caller": {"userId": "no-such-user"},
            },
        )
        assert r.status_code == 403
        assert r.json()["data"]["reason"] == "USER_NOT_FOUND"
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(GatewayDispatchLog).where(GatewayDispatchLog.run_id == "r2")
            )).scalars().one()
        assert row.result == "rejected"
        assert row.reject_reason == "USER_NOT_FOUND"
    finally:
        settings.GATEWAY_INTERNAL_TOKEN = saved


async def test_routes_by_user_id_and_audits_caller_agent_metadata(client):
    """caller 自报 agentId 仅作元数据：路由成功且审计行落 caller_agent_id。"""
    settings = get_settings()
    saved_token = settings.GATEWAY_INTERNAL_TOKEN
    saved_field = settings.GATEWAY_CALLER_USER_ID_FIELD
    settings.GATEWAY_INTERNAL_TOKEN = "test-gateway-token"
    settings.GATEWAY_CALLER_USER_ID_FIELD = "id"
    try:
        user_id = await seed_query_agent_for_user("qa_mgr")
        r = await client.post(
            "/api/v1/internal/gateway/resolve-caller",
            headers={"X-Gateway-Token": "test-gateway-token"},
            json={
                "runId": "r3", "capability": "query_control_platform",
                "input": {"path": "/external/orders/list"},
                "caller": {"agentId": "AG-CALLER-META", "userId": str(user_id)},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["mode"] == "user"
        assert body["data"]["userId"] == user_id
        assert body["data"]["actorToken"]
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(GatewayDispatchLog).where(GatewayDispatchLog.run_id == "r3")
            )).scalars().one()
        assert row.result == "routed"
        assert row.mode == "user"
        assert row.caller_agent_id == "AG-CALLER-META"
        assert row.resolved_user_id == user_id
    finally:
        settings.GATEWAY_INTERNAL_TOKEN = saved_token
        settings.GATEWAY_CALLER_USER_ID_FIELD = saved_field
