"""resolve-caller 内网端点：token 鉴权、403、审计。"""

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.agent.gateway import GatewayDispatchLog


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


async def test_rejects_unknown_agent_with_audit(client):
    settings = get_settings()
    saved = settings.GATEWAY_INTERNAL_TOKEN
    settings.GATEWAY_INTERNAL_TOKEN = "test-gateway-token"
    try:
        r = await client.post(
            "/api/v1/internal/gateway/resolve-caller",
            headers={"X-Gateway-Token": "test-gateway-token"},
            json={
                "runId": "r2", "capability": "query_control_platform", "input": {},
                "caller": {"agentId": "AG-999999"},
            },
        )
        assert r.status_code == 403
        assert r.json()["data"]["reason"] == "AGENT_NOT_FOUND"
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(GatewayDispatchLog).where(GatewayDispatchLog.run_id == "r2")
            )).scalars().one()
        assert row.result == "rejected"
        assert row.reject_reason == "AGENT_NOT_FOUND"
    finally:
        settings.GATEWAY_INTERNAL_TOKEN = saved
