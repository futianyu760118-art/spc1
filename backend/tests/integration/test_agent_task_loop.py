"""智能体中心集成测试：层级、能力授予、任务闭环、会话隔离与 actor 范围。"""

import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.basicdata.announcement import Notification
from app.models.basicdata.employee import Employee
from app.models.basicdata.organization import Organization
from app.models.basicdata.user import SysUser
from app.models.basicdata.user_org_scope import UserOrgScope
from app.models.order.sale_order import SaleOrder
from app.services.agent import task_tools
from app.services.agent.actor import issue_actor_token
from app.services.agent.context import get_or_create_agent, load_agent_context
from app.services.agent.scope import resolve_base_org_ids
from app.services.agent.task_service import create_task
from tests.conftest import login


async def _me(client, headers):
    r = await client.get("/api/v1/agents/me", headers=headers)
    return r.json()["data"]


async def _seed_shared_org(db, user_ids, suffix):
    from sqlalchemy import text
    await db.execute(
        text("DELETE FROM sys_user_org_scope WHERE user_id = ANY(:uids)"),
        {"uids": [int(uid) for uid in user_ids]},
    )
    org = Organization(
        org_code=f"ORG-AGT-{suffix}",
        org_name=f"智能体测试部-{suffix}",
        org_type="dept",
        status=1,
    )
    db.add(org)
    await db.flush()
    for user_id in user_ids:
        db.add(UserOrgScope(user_id=int(user_id), org_id=org.id, include_sub=True))
    await db.flush()
    return org


def _signed_headers(key, endpoint_code, query_string, actor_token=None):
    timestamp = int(time.time())
    string_to_sign = f"{timestamp}{key['app_key']}{endpoint_code}{query_string}"
    signature = hmac.new(
        key["app_secret"].encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    headers = {
        "X-App-Key": key["app_key"],
        "X-Timestamp": str(timestamp),
        "X-Signature": signature,
    }
    if actor_token:
        headers["X-Actor-Token"] = actor_token
    return headers


async def test_supervisor_task_loop_and_policy(client):
    headers_mgr = await login(client, "qa_mgr")
    headers_emp = await login(client, "qa_viewer")
    mgr = await _me(client, headers_mgr)
    emp = await _me(client, headers_emp)
    mgr_id = mgr["agent"]["user_id"]
    emp_id = emp["agent"]["user_id"]
    emp_agent_id = emp["agent"]["id"]

    r = await client.post(
        "/api/v1/agents/me/team", json={"user_id": emp_id}, headers=headers_mgr,
    )
    assert r.json()["code"] == 0, r.json()

    # 主管没有订单写权限，越权授予应 403
    r = await client.put(
        f"/api/v1/agents/me/team/{emp_agent_id}/policy",
        json={"granted": ["write.order_schedule"], "disabled": []},
        headers=headers_mgr,
    )
    assert r.json()["code"] == 403

    r = await client.put(
        f"/api/v1/agents/me/team/{emp_agent_id}/policy",
        json={"granted": ["query.orders"], "disabled": []},
        headers=headers_mgr,
    )
    assert r.json()["code"] == 0, r.json()
    emp_after = await _me(client, headers_emp)
    emp_caps = {item["code"] for item in emp_after["effective_capabilities"]}
    assert "query.orders" in emp_caps

    suffix = str(int(time.time() * 1000))[-6:]
    async with AsyncSessionLocal() as db:
        org = await _seed_shared_org(db, [mgr_id, emp_id], suffix)
        order_no = f"SO-AGT-{suffix}"
        db.add(SaleOrder(
            order_no=order_no, line_no="1", customer="智能体测试客户",
            product_code="P-AGT", order_qty=10, status="open",
            department=org.org_name, owner="qa_mgr",
        ))
        await db.commit()

        mgr_user = await db.get(SysUser, mgr_id)
        ctx = await load_agent_context(db, mgr_user, use_cache=False)
        task = await create_task(
            db, ctx,
            assignee_user_id=emp_id,
            title="跟进测试订单交期",
            description="请确认交期并反馈结论",
            due_at=datetime.now() + timedelta(days=2),
            priority="high",
            task_type="business",
            biz_type="order",
            biz_identifier=order_no,
        )
        await db.commit()
        task_id = task.id
        task_no = task.task_no

    async with AsyncSessionLocal() as db:
        notification = (await db.execute(
            select(Notification.id).where(
                Notification.ref_type == "agent_task",
                Notification.ref_id == task_id,
            ).limit(1)
        )).first()
        assert notification is not None

    r = await client.get("/api/v1/agents/me/tasks", headers=headers_emp)
    items = r.json()["data"]["items"]
    assert any(item["id"] == task_id for item in items)
    assert items[0]["biz_no"] == order_no

    r = await client.post(f"/api/v1/agents/tasks/{task_id}/start", headers=headers_emp)
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "in_progress", r.json()

    r = await client.post(
        f"/api/v1/agents/tasks/{task_id}/block",
        json={"reason": "等待客户确认"}, headers=headers_emp,
    )
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "blocked"

    r = await client.post(f"/api/v1/agents/tasks/{task_id}/resume", headers=headers_emp)
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "in_progress"

    # 员工不能取消任务
    r = await client.post(
        f"/api/v1/agents/tasks/{task_id}/cancel",
        json={"reason": "员工越权"}, headers=headers_emp,
    )
    assert r.json()["code"] == 403

    r = await client.post(
        f"/api/v1/agents/tasks/{task_id}/submit",
        json={"summary": "客户已确认，可按时交付", "result_data": {"conclusion": "可交付"}},
        headers=headers_emp,
    )
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "completed"

    # 非法状态迁移：已完成不能再开始/取消
    r = await client.post(f"/api/v1/agents/tasks/{task_id}/start", headers=headers_emp)
    assert r.json()["code"] == 400
    r = await client.post(
        f"/api/v1/agents/tasks/{task_id}/cancel",
        json={"reason": "完成后取消"}, headers=headers_mgr,
    )
    assert r.json()["code"] == 400

    r = await client.post(
        f"/api/v1/agents/tasks/{task_id}/reassign",
        json={"new_assignee_user_id": emp_id}, headers=headers_mgr,
    )
    assert r.json()["code"] == 400

    r = await client.get("/api/v1/agents/me/team/tasks/summary", headers=headers_mgr)
    assert r.json()["code"] == 0

    r = await client.post(
        f"/api/v1/agents/tasks/{task_id}/return",
        json={"reason": "请补充证据"}, headers=headers_mgr,
    )
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "in_progress"

    r = await client.patch(
        f"/api/v1/agents/tasks/{task_id}",
        json={"priority": "urgent"}, headers=headers_mgr,
    )
    assert r.json()["code"] == 0 and r.json()["data"]["priority"] == "urgent"

    r = await client.post(
        f"/api/v1/agents/tasks/{task_id}/cancel",
        json={"reason": "需求取消"}, headers=headers_mgr,
    )
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "cancelled"

    # 会话归属隔离
    r = await client.post(f"/api/v1/agents/tasks/{task_id}/conversation", headers=headers_emp)
    conv_id = r.json()["data"]["conversation_id"]
    r = await client.get(f"/api/v1/agents/me/conversations/{conv_id}", headers=headers_mgr)
    assert r.json()["code"] == 403

    # 任务事件与汇报审计仍在
    r = await client.get(f"/api/v1/agents/tasks/{task_id}", headers=headers_mgr)
    detail = r.json()["data"]
    assert detail["task_no"] == task_no
    assert any(event["event_type"] == "returned" for event in detail["events"])
    assert detail["reports"][0]["version"] == 1

    # 助手确认动作：准备确认卡 → 执行 → 新任务落库
    async with AsyncSessionLocal() as db:
        mgr_user = await db.get(SysUser, mgr_id)
        ctx = await load_agent_context(db, mgr_user, use_cache=False)
        prepared = await task_tools.prepare_confirmation(
            db, ctx, "assign_task",
            {
                "assignee_user_id": emp_id,
                "title": "确认卡派发任务",
                "due_at": (datetime.now() + timedelta(days=1)).isoformat(),
                "priority": "normal",
                "task_type": "general",
            },
        )
        assert prepared["preview"]["assignee_name"]
        result = await task_tools.execute_confirmed_action(
            db, user_id=mgr_id, action_data=prepared["action_data"],
        )
        await db.commit()
        confirmed_task_id = result["task"]["id"]
        assert result["task"]["status"] == "pending"

    r = await client.post(
        f"/api/v1/agents/tasks/{confirmed_task_id}/cancel",
        json={"reason": "确认卡测试收尾"}, headers=headers_mgr,
    )
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "cancelled"


async def test_concurrent_first_agent_create_is_idempotent(client):
    await login(client, "qa_viewer")

    async def create_once():
        async with AsyncSessionLocal() as db:
            user = (await db.execute(
                select(SysUser).where(SysUser.username == "qa_viewer")
            )).scalars().first()
            agent = await get_or_create_agent(db, user)
            await db.commit()
            return agent.id

    ids = await asyncio.gather(create_once(), create_once())
    assert ids[0] == ids[1]


async def test_org_scope_fails_closed_without_oa_mapping(client):
    await login(client, "qa_viewer")
    async with AsyncSessionLocal() as db:
        user = (await db.execute(
            select(SysUser).where(SysUser.username == "qa_viewer")
        )).scalars().first()
        await db.execute(
            text("DELETE FROM sys_user_org_scope WHERE user_id = :uid"), {"uid": user.id},
        )
        org = Organization(
            org_code=f"NM{int(time.time()) % 1000000}",
            org_name="无映射组织",
            org_type="dept",
            status=1,
            oa_org_id=None,
        )
        db.add(org)
        await db.flush()
        old_emp_code = user.emp_code
        user.emp_code = f"E-{int(time.time() * 1000)}"
        oa_org_id = 900000 + int(time.time()) % 100000
        emp = Employee(
            emp_code=user.emp_code, emp_name="映射测试员工", org_id=oa_org_id, status=1,
        )
        db.add(emp)
        await db.commit()
        try:
            # 1) OA org id 正确映射
            org.oa_org_id = str(oa_org_id)
            await db.commit()
            assert await resolve_base_org_ids(db, user) == {org.id}

            # 2) 员工 org_id 找不到组织：fail closed
            emp.org_id = 999999
            await db.commit()
            assert await resolve_base_org_ids(db, user) == set()

            # 3) 组织只有内部 id、没有 oa_org_id：不回退内部 id
            emp.org_id = org.id
            org.oa_org_id = None
            await db.commit()
            assert await resolve_base_org_ids(db, user) == set()
        finally:
            user.emp_code = old_emp_code
            await db.commit()


async def test_actor_token_scope_and_capability(client, ext_client, external_keys):
    headers_mgr = await login(client, "qa_mgr")
    headers_emp = await login(client, "qa_viewer")
    mgr = await _me(client, headers_mgr)
    emp = await _me(client, headers_emp)
    mgr_id = mgr["agent"]["user_id"]
    emp_id = emp["agent"]["user_id"]
    emp_agent_id = emp["agent"]["id"]

    await client.post("/api/v1/agents/me/team", json={"user_id": emp_id}, headers=headers_mgr)

    suffix = str(int(time.time() * 1000))[-6:]
    async with AsyncSessionLocal() as db:
        org = await _seed_shared_org(db, [mgr_id, emp_id], suffix)
        db.add_all([
            SaleOrder(order_no=f"SO-VIS-{suffix}", line_no="1", department=org.org_name,
                      owner="qa_viewer", status="open"),
            SaleOrder(order_no=f"SO-OUT-{suffix}", line_no="1", department="其它部门",
                      owner="other_user", status="open"),
        ])
        await db.commit()

    token = issue_actor_token(user_id=emp_id, agent_id=emp_agent_id, username="qa_viewer", role="viewer")
    params = {"page_size": 50}
    query_string = str(httpx.QueryParams(params))
    headers = _signed_headers(external_keys["orders"], "orders.list", query_string, token)
    r = await ext_client.get("/api/v1/external/orders/list", params=params, headers=headers)
    assert r.status_code == 403
    assert "能力" in r.json()["detail"]

    r = await client.put(
        f"/api/v1/agents/me/team/{emp_agent_id}/policy",
        json={"granted": ["query.orders"], "disabled": []},
        headers=headers_mgr,
    )
    assert r.json()["code"] == 0

    headers = _signed_headers(external_keys["orders"], "orders.list", query_string, token)
    r = await ext_client.get("/api/v1/external/orders/list", params=params, headers=headers)
    body = r.json()
    assert body["code"] == 0
    order_nos = {item["order_no"] for item in body["data"]["items"]}
    assert f"SO-VIS-{suffix}" in order_nos
    assert f"SO-OUT-{suffix}" not in order_nos
