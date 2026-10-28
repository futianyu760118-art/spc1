"""父 Agent -> 直属子 Agent 委派：成功、能力目录、拒绝与深度上限。"""

import pytest
from sqlalchemy import select

from app.models.agent.agent import AgentHierarchyLog
from app.models.agent.call import AgentCallLog
from app.models.basicdata.user import SysUser
from app.services.agent import delegation, delegation_tools, hierarchy
from app.services.agent.context import get_or_create_agent, load_agent_context


async def _seed_team(db):
    parent_user = (await db.execute(
        select(SysUser).where(SysUser.username == "qa_mgr")
    )).scalars().first()
    child_user = (await db.execute(
        select(SysUser).where(SysUser.username == "qa_viewer")
    )).scalars().first()
    parent = await get_or_create_agent(db, parent_user)
    parent.display_name = "主管智能体"
    parent.parent_agent_id = None
    parent.status = "active"
    parent.capability_policy = {"granted": ["query.orders"], "disabled": []}
    await db.flush()
    child = await get_or_create_agent(db, child_user)
    child.display_name = "子智能体"
    child.parent_agent_id = parent.id
    child.status = "active"
    child.capability_policy = {"granted": ["query.orders"], "disabled": []}
    await db.flush()
    parent_ctx = await load_agent_context(db, parent_user, use_cache=False)
    return parent, child, parent_user, child_user, parent_ctx


@pytest.mark.asyncio(loop_scope="session")
async def test_list_my_subordinates_exposes_capabilities(db):
    _parent, child, _parent_user, _child_user, parent_ctx = await _seed_team(db)
    result = await delegation_tools.execute_delegation_tool(
        db, parent_ctx, "list_my_subordinates", {},
        delegation_depth=0, max_delegation_depth=3, trace_id="trace-list",
    )
    assert result["ok"] is True
    item = next(row for row in result["items"] if row["agent_id"] == child.id)
    assert any(cap["code"] == "query.orders" for cap in item["capabilities"])
    await db.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_delegate_task_returns_child_result_and_writes_log(db, monkeypatch):
    _parent, child, _parent_user, child_user, parent_ctx = await _seed_team(db)

    async def fake_run_reaction(*args, **kwargs):
        yield "done", {
            "text": "SO-2026-001 交期风险 2 条。",
            "steps": [{"step_id": 1, "tool": "call_query_agent", "status": "completed"}],
            "diagnostics": {"total_tokens": 12},
            "failed": False,
        }

    monkeypatch.setattr(
        "app.services.assistant.orchestrator.run_reaction", fake_run_reaction,
    )
    result = await delegation.delegate_task(
        db,
        parent_ctx=parent_ctx,
        target_user_id=child_user.id,
        capability="query.orders",
        instruction="查一下 SO-2026-001 的交期风险",
        context={"order_no": "SO-2026-001"},
        trace_id="trace-delegate-success",
        delegation_depth=0,
        max_delegation_depth=3,
    )
    assert result["ok"] is True
    assert "交期风险" in result["summary"]
    log = (await db.execute(
        select(AgentCallLog).where(AgentCallLog.trace_id == "trace-delegate-success")
    )).scalars().first()
    assert log.status == "success"
    assert int(log.callee_agent_id) == int(child.id)
    await db.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_delegate_task_rejects_non_direct_child(db):
    _parent, _child, parent_user, _child_user, parent_ctx = await _seed_team(db)
    result = await delegation.delegate_task(
        db,
        parent_ctx=parent_ctx,
        target_user_id=parent_user.id,
        capability="query.orders",
        instruction="查订单",
        context={},
        trace_id="trace-delegate-reject",
        delegation_depth=0,
        max_delegation_depth=3,
    )
    assert result["ok"] is False
    assert "直属" in result["error"]
    await db.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_delegate_task_rejects_depth_limit(db):
    _parent, _child, _parent_user, child_user, parent_ctx = await _seed_team(db)
    result = await delegation.delegate_task(
        db,
        parent_ctx=parent_ctx,
        target_user_id=child_user.id,
        capability="query.orders",
        instruction="查订单",
        context={},
        trace_id="trace-delegate-depth",
        delegation_depth=3,
        max_delegation_depth=3,
    )
    assert result["ok"] is False
    assert "层级" in result["error"]
    await db.rollback()

@pytest.mark.asyncio(loop_scope="session")
async def test_supervisor_removes_direct_child_and_audits(db):
    _parent, child, _parent_user, _child_user, parent_ctx = await _seed_team(db)
    result = await hierarchy.remove_subordinate(db, parent_ctx, child.id)
    await db.refresh(child)
    assert child.parent_agent_id is None
    assert result["agent_id"] == child.id
    log = (await db.execute(
        select(AgentHierarchyLog)
        .where(AgentHierarchyLog.agent_id == child.id)
        .order_by(AgentHierarchyLog.id.desc())
    )).scalars().first()
    assert log.action == "unbind"
    assert log.old_parent_id == parent_ctx.agent.id
    await db.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_supervisor_cannot_remove_non_direct_agent(db):
    parent, _child, _parent_user, _child_user, parent_ctx = await _seed_team(db)
    with pytest.raises(hierarchy.HierarchyError):
        await hierarchy.remove_subordinate(db, parent_ctx, parent.id)
    await db.rollback()
