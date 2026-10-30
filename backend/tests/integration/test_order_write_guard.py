"""审查修复回归：反馈工具端到端（校验/撤销）、确认执行前字段能力复核。"""

import pytest

from app.core.database import AsyncSessionLocal
from app.models.basicdata.user import SysUser
from app.services.agent.context import TeamMemberInfo, UserContext
from app.services.assistant import orchestrator
from app.services.assistant.agent_tools import execute_agent_tool
from tests.conftest import check_team_member, get_user_id_by_username, insert_catalog_agent


def _user_context(user: SysUser, capabilities) -> UserContext:
    return UserContext(
        user=user, role_code="admin", permissions={"topbar.feedback": ["read"]},
        members=[TeamMemberInfo(
            agent_id=1, agent_no="AG-1", display_name="服务台",
            capabilities=list(capabilities), description=None, status="active", config_version=1,
        )],
        effective_capabilities=set(capabilities),
        allowed_tools={"create_feedback", "revoke_feedback"},
    )


async def test_feedback_tool_create_revoke_and_validation(_test_db):
    async with AsyncSessionLocal() as db:
        user_id = await get_user_id_by_username("qa_fin")
        user = await db.get(SysUser, user_id)
        ctx = _user_context(user, ["write.feedback_create"])

        out = await execute_agent_tool(
            "create_feedback",
            {"title": "页面报错", "description": "保存时报 500", "type": "suggestion", "severity": "high"},
            db=db, user_context=ctx,
        )
        assert out["ok"], out
        fid = out["result"]["feedback_id"]
        assert out["result"]["severity"] == "high"

        bad_severity = await execute_agent_tool(
            "create_feedback",
            {"title": "t", "description": "d", "severity": "urgent"},
            db=db, user_context=ctx,
        )
        assert not bad_severity["ok"] and "严重程度非法" in bad_severity["error"]

        too_long = await execute_agent_tool(
            "create_feedback",
            {"title": "x" * 201, "description": "d"},
            db=db, user_context=ctx,
        )
        assert not too_long["ok"] and "200" in too_long["error"]

        revoked = await execute_agent_tool(
            "revoke_feedback", {"feedback_id": fid}, db=db, user_context=ctx,
        )
        assert revoked["ok"] and revoked["result"]["deleted"] == fid
        await db.rollback()


async def test_confirm_write_rechecks_field_capability(_test_db, monkeypatch):
    async def noop_resolve(db, biz_type, biz_no):
        return {}

    monkeypatch.setattr(orchestrator, "resolve_business_object", noop_resolve)

    user_id = await get_user_id_by_username("qa_fin")
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError) as no_cap:
            await orchestrator._prepare_order_write_actor(
                db, str(user_id), "HJ-1", {"planned_start_date": "2026-11-01"},
            )
        assert "写入能力" in str(no_cap.value)

        agent_id = await insert_catalog_agent(
            db, agent_no="AG-TEST-WRITE", name="计划写入员",
            capabilities=["write.order_planned_start"],
        )
        await check_team_member(db, user_id=user_id, agent_id=agent_id)
        await db.flush()

        token = await orchestrator._prepare_order_write_actor(
            db, str(user_id), "HJ-1", {"planned_start_date": "2026-11-01"},
        )
        assert token

        with pytest.raises(ValueError) as denied:
            await orchestrator._prepare_order_write_actor(
                db, str(user_id), "HJ-1", {"customer_inspection_date": "2026-11-01"},
            )
        assert "customer_inspection_date" in str(denied.value)
        await db.rollback()
