"""采购申请单闭环集成测试（MRP P2）。

覆盖：未配置审批链提交被拒 → 配置链 → 提交 → 审批中心聚合 / preview / 审批通过 →
转 SPC 采购订单（purchase_order 反写断言）→ 单据关闭；驳回后编辑重新提交；配置可见性。
"""

from datetime import date

import pytest_asyncio
from sqlalchemy import delete, select, text

from tests.conftest import login
from tests.integration._helpers import PM

ADMIN = "admin"
MATERIAL_CODE = "PYTEST-PR-001"
NEED_DATE = "2026-10-15"
CHAIN = [{"seq": 1, "label": "采购确认", "role": "purchase_manager"}]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _requisition_material(_test_db):
    """种入申请单解析所需的物料主数据；编码唯一 upsert，不参与每例清表。"""
    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO scm_material
                (erp_material_id, material_code, material_name, spec_model,
                 material_type, unit_of_measure, order_unit_price,
                 is_purchase, is_produce, erp_sync_flag, is_deleted, status)
            VALUES (990001, :code, 'pytest 采购申请物料', 'SPEC-990001', '外购', 'PCS', 12.5,
                    1, 0, 0, 0, 1)
            ON CONFLICT (material_code) DO UPDATE
                SET material_name = EXCLUDED.material_name, is_deleted = 0
        """), {"code": MATERIAL_CODE})


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _mrp_exception_table(_test_db):
    """mrp_exception 不在 conftest 最小表集合中，本模块用例自建（幂等）。"""
    from app.core.database import Base, engine
    from app.models.mrp.exception import MrpException

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[MrpException.__table__])


async def _configure_chain(client, headers):
    r = await client.put("/api/v1/approvals/configs/purchase_requisition",
                         json={"nodes": CHAIN}, headers=headers)
    assert r.json()["code"] == 0, r.text


async def _drop_chain():
    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM approval_config WHERE biz_type = 'purchase_requisition'"
        ))


async def _create_req(client, headers, qty=10):
    r = await client.post("/api/v1/materials/purchase-requisitions", json={
        "department": "采购部",
        "remark": "pytest 闭环",
        "lines": [{"material_code": MATERIAL_CODE, "req_qty": qty, "need_date": NEED_DATE}],
    }, headers=headers)
    assert r.json()["code"] == 0, r.text
    return r.json()["data"]


async def _get_detail(client, headers, req_id):
    r = await client.get(f"/api/v1/materials/purchase-requisitions/{req_id}", headers=headers)
    assert r.json()["code"] == 0, r.text
    return r.json()["data"]


async def _submit(client, headers, req_id):
    return await client.post(f"/api/v1/materials/purchase-requisitions/{req_id}/submit",
                             headers=headers)


async def _approved_req(client, h_admin, h_pm, qty=10):
    req = await _create_req(client, h_admin, qty=qty)
    assert (await _submit(client, h_admin, req["id"])).json()["code"] == 0
    r = await client.post(f"/api/v1/approvals/items/purchase_requisition/{req['id']}/approve",
                          json={"comment": "同意"}, headers=h_pm)
    assert r.json()["code"] == 0, r.text
    return req


async def test_requisition_submit_requires_chain(client):
    """审批链未配置时提交返回 400 且文案含「审批链未配置」，单据保持草稿。"""
    await _drop_chain()
    h_admin = await login(client, ADMIN)
    req = await _create_req(client, h_admin)

    r = await _submit(client, h_admin, req["id"])
    assert r.status_code == 400, r.text
    assert "审批链未配置" in r.json()["detail"]
    assert (await _get_detail(client, h_admin, req["id"]))["status"] == "draft"


async def test_requisition_full_flow(client, db):
    """配置链 → 提交 → 聚合待办 → preview → 审批通过 → 转 PO 全量 → 单据关闭。"""
    h_admin = await login(client, ADMIN)
    await _configure_chain(client, h_admin)
    h_pm = await login(client, PM)
    req = await _create_req(client, h_admin, qty=10)

    r = await _submit(client, h_admin, req["id"])
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "approving"

    r = await client.get("/api/v1/approvals/pending",
                         params={"biz_type": "purchase_requisition"}, headers=h_pm)
    hit = [x for x in r.json()["data"]["items"] if x["id"] == req["id"]]
    assert len(hit) == 1
    assert hit[0]["no"] == req["req_no"]
    assert hit[0]["biz_name"] == "采购申请单"
    assert hit[0]["deep_link"] == f"/purchase-requisitions/{req['id']}"
    assert hit[0]["current_node"] == "采购确认"

    r = await client.get(f"/api/v1/approvals/items/purchase_requisition/{req['id']}", headers=h_pm)
    preview = r.json()["data"]
    assert [f["label"] for f in preview["fields"]][0] == "申请单号"
    assert preview["fields"][0]["value"] == req["req_no"]
    assert preview["can_act"] is True

    r = await client.post(f"/api/v1/approvals/items/purchase_requisition/{req['id']}/approve",
                          json={"comment": "同意"}, headers=h_pm)
    assert r.json()["code"] == 0 and r.json()["data"]["finished"] is True
    assert (await _get_detail(client, h_admin, req["id"]))["status"] == "approved"

    detail = await _get_detail(client, h_admin, req["id"])
    line_id = detail["lines"][0]["id"]
    r = await client.post(f"/api/v1/materials/purchase-requisitions/{req['id']}/convert-to-po",
                          json={"items": [{"line_id": line_id, "qty": 10}]}, headers=h_admin)
    body = r.json()
    assert body["code"] == 0, body
    assert body["data"] == {"created": 1, "closed": True}

    po_no = f"MRP-{req['req_no']}-1"
    po = (await db.execute(text(
        "SELECT po_no, data_source, eta, po_qty, material_code "
        "FROM purchase_order WHERE po_no = :p"
    ), {"p": po_no})).mappings().one()
    assert po["data_source"] == "mrp"
    assert po["eta"] == date(2026, 10, 15)
    assert float(po["po_qty"]) == 10
    assert po["material_code"] == MATERIAL_CODE

    detail = await _get_detail(client, h_admin, req["id"])
    assert detail["status"] == "closed"
    line = detail["lines"][0]
    assert line["status"] == "closed"
    assert line["converted_po_no"] == po_no
    assert line["converted_qty"] == 10

    r = await client.post(f"/api/v1/materials/purchase-requisitions/{req['id']}/convert-to-po",
                          json={"items": [{"line_id": line_id, "qty": 1}]}, headers=h_admin)
    assert r.status_code == 409
    assert "审批通过" in r.json()["detail"]


async def test_requisition_reject_then_resubmit(client):
    """驳回 → rejected → 编辑（明细整体替换）→ 再提交 → approving，两轮提交留档。"""
    h_admin = await login(client, ADMIN)
    await _configure_chain(client, h_admin)
    h_pm = await login(client, PM)
    req = await _create_req(client, h_admin, qty=5)
    assert (await _submit(client, h_admin, req["id"])).json()["code"] == 0

    r = await client.post(f"/api/v1/approvals/items/purchase_requisition/{req['id']}/reject",
                          json={"comment": "数量有误"}, headers=h_pm)
    assert r.json()["code"] == 0, r.text
    detail = await _get_detail(client, h_admin, req["id"])
    assert detail["status"] == "rejected"
    assert any(lg["action"] == "reject" and lg["comment"] == "数量有误"
               for lg in detail["approval_logs"])

    r = await client.put(f"/api/v1/materials/purchase-requisitions/{req['id']}", json={
        "remark": "已修正",
        "lines": [{"material_code": MATERIAL_CODE, "req_qty": 8, "need_date": NEED_DATE}],
    }, headers=h_admin)
    assert r.json()["code"] == 0, r.text
    assert r.json()["data"]["lines"][0]["req_qty"] == 8

    r = await _submit(client, h_admin, req["id"])
    assert r.json()["code"] == 0 and r.json()["data"]["status"] == "approving"
    detail = await _get_detail(client, h_admin, req["id"])
    assert [lg["action"] for lg in detail["approval_logs"]].count("submit") == 2


async def test_requisition_config_visible(client):
    """审批链配置列表可见内置注册的 purchase_requisition 及其条件字段。"""
    h_admin = await login(client, ADMIN)
    r = await client.get("/api/v1/approvals/configs", headers=h_admin)
    item = next((x for x in r.json()["data"]["items"] if x["biz_type"] == "purchase_requisition"), None)
    assert item is not None
    assert item["biz_name"] == "采购申请单"
    assert item["mode"] == "builtin"
    assert item["condition_field_options"] == []


async def test_convert_requires_open_line(client, db):
    """明细行已关闭转单 → 409；正常行转单成功后重复转单 → 409（主表已关闭）。"""
    from app.models.material.purchase_requisition import PurchaseRequisitionLine

    h_admin = await login(client, ADMIN)
    await _configure_chain(client, h_admin)
    h_pm = await login(client, PM)

    closed_req = await _approved_req(client, h_admin, h_pm, qty=10)
    closed_line_id = (await _get_detail(client, h_admin, closed_req["id"]))["lines"][0]["id"]
    line = await db.get(PurchaseRequisitionLine, closed_line_id)
    line.status = "closed"
    await db.commit()

    r = await client.post(
        f"/api/v1/materials/purchase-requisitions/{closed_req['id']}/convert-to-po",
        json={"items": [{"line_id": closed_line_id, "qty": 1}]}, headers=h_admin)
    assert r.status_code == 409, r.text
    assert "已关闭" in r.json()["detail"]

    open_req = await _approved_req(client, h_admin, h_pm, qty=10)
    open_line_id = (await _get_detail(client, h_admin, open_req["id"]))["lines"][0]["id"]
    url = f"/api/v1/materials/purchase-requisitions/{open_req['id']}/convert-to-po"
    r = await client.post(url, json={"items": [{"line_id": open_line_id, "qty": 10}]},
                          headers=h_admin)
    assert r.json()["code"] == 0, r.text
    r = await client.post(url, json={"items": [{"line_id": open_line_id, "qty": 10}]},
                          headers=h_admin)
    assert r.status_code == 409, r.text
    assert "审批通过" in r.json()["detail"]


async def test_exception_handle_actions(client, db):
    """例外动作：notify 仅限催货类型、ignore 生效、only_late 只返回 late/early。"""
    from app.models.mrp.exception import MrpException

    h_admin = await login(client, ADMIN)
    run_id = 990001
    await db.execute(delete(MrpException).where(MrpException.run_id == run_id))
    demand = MrpException(
        run_id=run_id, material_id=1, material_code="PYTEST-MRP-1",
        material_name="pytest 例外物料", exception_code=6, exception_type="past_due_demand",
        source_type="sale_order_line", source_doc_no="SO-1", source_line_no="1", status="open",
    )
    late = MrpException(
        run_id=run_id, material_id=1, material_code="PYTEST-MRP-1",
        material_name="pytest 例外物料", exception_code=11, exception_type="supply_late",
        source_type="po", source_doc_no="PO-1", status="open",
    )
    db.add_all([demand, late])
    await db.flush()
    demand_id, late_id = demand.id, late.id
    await db.commit()

    r = await client.get("/api/v1/mrp/exceptions",
                         params={"run_id": run_id, "only_late": "true"}, headers=h_admin)
    assert r.json()["code"] == 0, r.text
    assert [x["exception_type"] for x in r.json()["data"]["items"]] == ["supply_late"]

    r = await client.get("/api/v1/mrp/exceptions", params={"run_id": run_id}, headers=h_admin)
    assert r.json()["data"]["total"] == 2

    r = await client.post("/api/v1/mrp/exceptions/batch-handle",
                          json={"exception_ids": [demand_id, late_id], "action": "notify"},
                          headers=h_admin)
    assert r.json()["code"] == 0, r.text
    assert r.json()["data"] == {
        "updated": 1,
        "skipped": [{"id": demand_id, "reason": "该类型不支持催货"}],
    }

    r = await client.post("/api/v1/mrp/exceptions/batch-handle",
                          json={"exception_ids": [demand_id, late_id], "action": "ignore"},
                          headers=h_admin)
    assert r.json()["data"] == {"updated": 2, "skipped": []}

    statuses = (await db.execute(
        select(MrpException.status).where(MrpException.run_id == run_id)
    )).scalars().all()
    assert set(statuses) == {"ignored"}
