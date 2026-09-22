"""审批中心 API 回归测试（统一待我审批聚合 / 审批链配置 / 角色选项）。"""

from tests.conftest import login
from tests.integration._helpers import PM, Q, VIEWER, act, create, pending_items, snap_roles

ADMIN = "admin"


async def test_pending_aggregates_supplier_claim(client):
    """统一待审批聚合索赔单条目，字段与深链完整。"""
    h_q, h_pm = await login(client, Q), await login(client, PM)
    a = await create(client, h_q, 500, submit=True)
    items = await pending_items(client, h_pm)
    hit = [x for x in items if x["id"] == a["id"]]
    assert len(hit) == 1
    item = hit[0]
    assert item["biz_type"] == "supplier_claim" and item["biz_name"] == "供应商索赔单"
    assert item["no"] == a["claim_no"]
    assert item["title"] == a["supplier_name"]
    assert item["deep_link"] == f"/quality/supplier-claims/{a['id']}"
    assert item["current_node"] == "索赔部门意见"
    assert item["current_level"] == 1
    assert item["submitted_at"]


async def test_pending_requires_approval_permission(client):
    """无 approval.pending 权限的角色访问统一待审批 → 403。"""
    h_viewer = await login(client, VIEWER)
    r = await client.get("/api/v1/approvals/pending", headers=h_viewer)
    assert r.status_code == 403


async def test_pending_admin_sees_all_nodes(client):
    """admin 旁路节点权限，任何节点都能看到。"""
    h_q, h_admin = await login(client, Q), await login(client, ADMIN)
    a = await create(client, h_q, 2000, submit=True)  # 当前节点=采购经理
    items = await pending_items(client, h_admin)
    assert any(x["id"] == a["id"] for x in items)


async def test_configs_list_includes_registered_biz(client):
    h_admin = await login(client, ADMIN)
    r = await client.get("/api/v1/approvals/configs", headers=h_admin)
    items = r.json()["data"]["items"]
    sc = next((x for x in items if x["biz_type"] == "supplier_claim"), None)
    assert sc is not None and sc["biz_name"] == "供应商索赔单"
    assert len(sc["nodes"]) == 4


async def test_config_save_via_center_takes_effect(client):
    """经审批中心保存的审批链，对之后重新提交的单据生效。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    nodes = [{"seq": 1, "label": "单级确认", "role": "quality"}]
    r = await client.put("/api/v1/approvals/configs/supplier_claim", json={"nodes": nodes}, headers=h_admin)
    assert r.json()["code"] == 0
    a = await create(client, h_q, 100, submit=True)
    assert await snap_roles(a) == ["quality"]
    r = await act(client, h_q, a["id"], "approve")
    assert r.json()["code"] == 0 and r.json()["data"].get("finished") is True


async def test_config_unregistered_biz_rejected(client):
    """未注册到审批中心的 biz_type（如调价单）不可经统一入口改配置，防双写路径。"""
    h_admin = await login(client, ADMIN)
    r = await client.put("/api/v1/approvals/configs/price_change", json={"nodes": []}, headers=h_admin)
    assert r.json()["code"] == 1
    r = await client.get("/api/v1/approvals/configs/price_change", headers=h_admin)
    assert r.json()["code"] == 1


async def test_roles_endpoint_lists_system_roles(client):
    h_admin = await login(client, ADMIN)
    r = await client.get("/api/v1/approvals/roles", headers=h_admin)
    codes = {x["role_code"] for x in r.json()["data"]["items"]}
    assert {"admin", "quality", "purchase_manager", "manager", "finance", "general_manager"} <= codes


async def test_roles_requires_config_permission(client):
    """角色下拉走审批域自有权限：无 approval.config 的角色 403。"""
    h_pm = await login(client, PM)
    r = await client.get("/api/v1/approvals/roles", headers=h_pm)
    assert r.status_code == 403
