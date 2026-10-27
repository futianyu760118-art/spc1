"""网关 resolver：agentId/userId/系统级/拒绝 + 审计行。"""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.agent.gateway import GatewayDispatchLog
from app.models.basicdata.user import SysUser
from app.services.agent.actor import decode_actor_token
from app.services.agent.gateway_resolver import resolve_dispatch

pytestmark = pytest.mark.usefixtures("_test_db")


@pytest.fixture
def user_id_field():
    settings = get_settings()
    saved = settings.GATEWAY_CALLER_USER_ID_FIELD
    settings.GATEWAY_CALLER_USER_ID_FIELD = "id"
    yield settings
    settings.GATEWAY_CALLER_USER_ID_FIELD = saved


async def _user_id_with_agent(username: str) -> int:
    from app.services.agent.context import get_or_create_agent
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(SysUser).where(SysUser.username == username))).scalars().one()
        await get_or_create_agent(db, user, created_by_user_id=user.id)
        await db.commit()
        return int(user.id)


async def test_resolve_by_user_id(user_id_field):
    user_id = await _user_id_with_agent("qa_mgr")
    async with AsyncSessionLocal() as db:
        result = await resolve_dispatch(
            db, run_id="run-1", trace_id="trace-1",
            capability="query_control_platform",
            input_data={"path": "/external/orders/list"},
            caller={"systemId": "aeos-hub", "userId": str(user_id), "traceId": "trace-1"},
        )
        await db.commit()
    assert result.ok is True
    assert result.mode == "user"
    assert decode_actor_token(result.actor_token)["user_id"] == user_id


async def test_resolve_rejects_unknown_agent(user_id_field):
    async with AsyncSessionLocal() as db:
        result = await resolve_dispatch(
            db, run_id="run-2", trace_id="trace-2",
            capability="query_control_platform",
            input_data={}, caller={"agentId": "AG-999999"},
        )
        await db.commit()
        row = (await db.execute(
            select(GatewayDispatchLog).where(GatewayDispatchLog.run_id == "run-2")
        )).scalars().one()
    assert result.ok is False
    assert result.reject_reason == "AGENT_NOT_FOUND"
    assert row.result == "rejected"


async def test_resolve_system_mode(user_id_field):
    async with AsyncSessionLocal() as db:
        result = await resolve_dispatch(
            db, run_id="run-3", trace_id="trace-3",
            capability="query_control_platform", input_data={}, caller=None,
        )
        await db.commit()
    assert result.ok is True
    assert result.mode == "system"
    assert result.actor_token is None


@pytest.mark.parametrize(
    ("field", "stored", "caller_value"),
    [
        ("emp_code", "E9001", "E9001"),
        ("wecom_user_id", "wx-u9001", "wx-u9001"),
        ("scm_employee_id", 9001, "9001"),
    ],
)
async def test_resolve_by_configurable_user_field(field, stored, caller_value):
    user_id = await _user_id_with_agent("qa_mgr")
    settings = get_settings()
    saved = settings.GATEWAY_CALLER_USER_ID_FIELD
    settings.GATEWAY_CALLER_USER_ID_FIELD = field
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(SysUser, user_id)
            setattr(user, field, stored)
            await db.commit()
            result = await resolve_dispatch(
                db, run_id=f"run-{field}", trace_id=f"trace-{field}",
                capability="query_control_platform",
                input_data={"path": "/external/orders/list"},
                caller={"systemId": "aeos-hub", "userId": caller_value},
            )
            await db.commit()
        assert result.ok is True
        assert result.mode == "user"
        assert decode_actor_token(result.actor_token)["user_id"] == user_id
    finally:
        settings.GATEWAY_CALLER_USER_ID_FIELD = saved


async def test_audit_failure_fails_closed(monkeypatch):
    async with AsyncSessionLocal() as db:
        def _boom(*args, **kwargs):
            raise RuntimeError("audit down")

        monkeypatch.setattr(
            "app.services.agent.gateway_resolver._audit", _boom,
        )
        with pytest.raises(RuntimeError):
            await resolve_dispatch(
                db, run_id="run-audit", trace_id=None,
                capability="query_control_platform", input_data={}, caller=None,
            )
