"""审批中心中心化核心链路集成测试（Task 11 新增）。

覆盖：提交展开任务与待办可见性 → 审批到终态同步业务行 → 驳回必填意见+流水 →
已办/发起 Tab → 声明式业务全链路（注册 → 中心提交 → 审批 → 回写）。
"""

from sqlalchemy import text

from tests.conftest import login
from tests.integration._helpers import FIN, GM, PM, Q, create


async def _submit_claim(client, headers, amount=500) -> dict:
    """创建并提交一张索赔单（builtin Adapter 经中心提交）。"""
    return await create(client, headers, amount, submit=True)


async def test_submit_expands_tasks_and_pending_list(client):
    """提交后节点任务展开到人：节点1（purchase_manager）持有人可见待办，其他人不可见。"""
    h_q = await login(client, Q)
    claim = await _submit_claim(client, h_q)
    pm = await login(client, PM)
    r = await client.get("/api/v1/approvals/pending", headers=pm)
    items = r.json()["data"]["items"]
    hit = [it for it in items if it["biz_type"] == "supplier_claim" and it["id"] == claim["id"]]
    assert len(hit) == 1 and hit[0]["can_act"] is True
    gm = await login(client, GM)
    r = await client.get("/api/v1/approvals/pending", headers=gm)
    assert not any(it["id"] == claim["id"] for it in r.json()["data"]["items"])


async def test_approve_finishes_and_syncs_business_row(client, db):
    """逐级审批到终态：中心归档同时经 on_transition 同步业务表旧列（回滚安全锚点）。"""
    h_q = await login(client, Q)
    claim = await _submit_claim(client, h_q, amount=500)  # < 1000：经理/总经理节点均被条件过滤
    pm = await login(client, PM)
    r = await client.post(f"/api/v1/approvals/items/supplier_claim/{claim['id']}/approve",
                          headers=pm, json={"comment": "同意"})
    assert r.json().get("code") == 0 and r.json()["data"]["finished"] is False, r.json()
    fin = await login(client, FIN)
    r = await client.post(f"/api/v1/approvals/items/supplier_claim/{claim['id']}/approve",
                          headers=fin, json={"comment": "结算通过"})
    body = r.json()
    assert body.get("code") == 0 and body["data"]["finished"] is True, body
    row = (await db.execute(text(
        "SELECT approval_status, approved_by FROM supplier_claim WHERE id = :i"),
        {"i": claim["id"]})).fetchone()
    assert row[0] == "approved" and row[1] == "qa_fin"


async def test_reject_requires_comment_and_writes_record(client, db):
    """驳回必填意见：空白意见被拒；有效驳回写中心流水 approval_record。"""
    h_q = await login(client, Q)
    claim = await _submit_claim(client, h_q)
    pm = await login(client, PM)
    r = await client.post(f"/api/v1/approvals/items/supplier_claim/{claim['id']}/reject",
                          headers=pm, json={"comment": "  "})
    assert r.json().get("code") == 1 and "意见" in r.json()["message"]
    r = await client.post(f"/api/v1/approvals/items/supplier_claim/{claim['id']}/reject",
                          headers=pm, json={"comment": "证据不足"})
    assert r.json().get("code") == 0, r.json()
    cnt = (await db.execute(text(
        "SELECT COUNT(*) FROM approval_record r JOIN approval_instance i ON i.id = r.instance_id"
        " WHERE i.biz_type='supplier_claim' AND i.biz_id=:i AND r.action='reject'"),
        {"i": claim["id"]})).scalar()
    assert cnt == 1


async def test_my_approved_and_submitted_tabs(client):
    """在途视角：审批人「我已审批」可见动作与意见，发起人「我发起的」仍为 pending。"""
    h_q = await login(client, Q)
    claim = await _submit_claim(client, h_q)
    pm = await login(client, PM)
    await client.post(f"/api/v1/approvals/items/supplier_claim/{claim['id']}/approve",
                      headers=pm, json={"comment": "ok"})
    r = await client.get("/api/v1/approvals/approved", headers=pm)
    items = r.json()["data"]["items"]
    assert any(it["id"] == claim["id"] and it["my_action"] == "approve"
               and it["my_comment"] == "ok" for it in items)
    r = await client.get("/api/v1/approvals/submitted", headers=h_q)
    items = r.json()["data"]["items"]
    assert any(it["id"] == claim["id"] and it["status"] == "pending" for it in items)


PAY_BIZ = "pytest_pay"
PAY_TABLE = "pytest_pay_app"


def _pay_business_payload() -> dict:
    return {
        "biz_type": PAY_BIZ, "biz_name": "测试付款", "sql_text":
            "SELECT id, pay_no AS no, pay_no AS title, applicant, submit_time AS submitted_at,"
            " node_label AS current_node, amt AS amount FROM pytest_pay_app",
        "field_mapping": {"id": "id", "no": "no", "title": "title", "applicant": "applicant",
                          "submitted_at": "submitted_at", "current_node": "current_node"},
        "condition_fields": [], "deep_link_template": "",
        "writeback": {"table": PAY_TABLE, "id_column": "id",
                      "status_column": "status",
                      "status_map": {"pending": "1", "approved": "2", "rejected": "3", "recalled": "0"}},
    }


async def _drop_pay_business(db):
    """清理声明式用例的注册/链配置/源表，避免污染其它用例与重复运行。"""
    await db.execute(text("DELETE FROM approval_business WHERE biz_type = :bt"), {"bt": PAY_BIZ})
    await db.execute(text("DELETE FROM approval_config WHERE biz_type = :bt"), {"bt": PAY_BIZ})
    await db.execute(text(f"DROP TABLE IF EXISTS {PAY_TABLE}"))
    await db.commit()


async def test_declarative_business_full_cycle(client, db):
    """SQL 声明式业务全链路：向导式注册 + 中心提交 + 审批 + 回写 + 待办可见。"""
    await db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {PAY_TABLE} (
            id SERIAL PRIMARY KEY, pay_no VARCHAR(64), applicant VARCHAR(64),
            status VARCHAR(16) DEFAULT '0', node_label VARCHAR(64), submit_time TIMESTAMP, amt NUMERIC
        )
    """))
    await db.execute(text(f"TRUNCATE {PAY_TABLE} RESTART IDENTITY"))
    await db.execute(text(
        f"INSERT INTO {PAY_TABLE} (pay_no, applicant, node_label, submit_time, amt)"
        " VALUES ('PAY001', 'qa_quality', '初审', NOW(), 500)"))
    await db.commit()
    try:
        admin = await login(client, "admin")
        r = await client.post("/api/v1/approvals/businesses", headers=admin,
                              json=_pay_business_payload())
        assert r.json().get("code") == 0, r.json()
        r = await client.put(f"/api/v1/approvals/configs/{PAY_BIZ}", headers=admin,
                             json={"nodes": [{"seq": 1, "label": "初审", "role": "purchase_manager"}],
                                   "is_active": True})
        assert r.json().get("code") == 0, r.json()

        user = await login(client, Q)
        r = await client.post("/api/v1/approvals/instances", headers=user,
                              json={"biz_type": PAY_BIZ, "biz_id": 1})
        assert r.json().get("code") == 0, r.json()
        st = (await db.execute(text(f"SELECT status FROM {PAY_TABLE} WHERE id = 1"))).scalar()
        assert st == "1"  # 提交即回写

        pm = await login(client, PM)
        r = await client.get("/api/v1/approvals/pending",
                             params={"biz_type": PAY_BIZ}, headers=pm)
        items = r.json()["data"]["items"]
        assert len(items) == 1 and items[0]["no"] == "PAY001" and items[0]["can_act"] is True

        r = await client.post(f"/api/v1/approvals/items/{PAY_BIZ}/1/approve",
                              headers=pm, json={"comment": "ok"})
        assert r.json().get("code") == 0 and r.json()["data"]["finished"] is True, r.json()
        st = (await db.execute(text(f"SELECT status FROM {PAY_TABLE} WHERE id = 1"))).scalar()
        assert st == "2"  # 回写映射生效
    finally:
        await _drop_pay_business(db)


async def _center_counts(db, biz_type: str, biz_id: int) -> tuple[int, int, int]:
    row = (await db.execute(text(
        "SELECT (SELECT COUNT(*) FROM approval_instance WHERE biz_type=:bt AND biz_id=:bid),"
        " (SELECT COUNT(*) FROM approval_task t JOIN approval_instance i ON i.id=t.instance_id"
        "  WHERE i.biz_type=:bt AND i.biz_id=:bid),"
        " (SELECT COUNT(*) FROM approval_record r JOIN approval_instance i ON i.id=r.instance_id"
        "  WHERE i.biz_type=:bt AND i.biz_id=:bid)"),
        {"bt": biz_type, "bid": biz_id})).fetchone()
    return row[0], row[1], row[2]


async def test_migrate_script_recovers_legacy_and_is_idempotent(client, db):
    """存量迁移：业务表有审批列、中心无实例的旧数据 → 导入恢复在途可见性；重跑幂等。"""
    from migrate_approval_center import main as migrate_main
    h_q = await login(client, Q)
    claim = await _submit_claim(client, h_q)
    cid = claim["id"]
    # 模拟存量状态：抹掉中心三表，回填一条旧引擎时代的 submit 日志
    await db.execute(text("DELETE FROM approval_record"))
    await db.execute(text("DELETE FROM approval_task"))
    await db.execute(text("DELETE FROM approval_instance"))
    await db.execute(text(
        "INSERT INTO supplier_claim_approval_log (claim_id, approval_level, approver, action, comment, operated_at)"
        " VALUES (:c, NULL, :ap, 'submit', '提交审批', NOW())"), {"c": cid, "ap": Q})
    await db.commit()
    pm = await login(client, PM)
    r = await client.get("/api/v1/approvals/pending", headers=pm)
    assert not any(it["id"] == cid for it in r.json()["data"]["items"])  # 中心无实例 → 待办消失

    await migrate_main()
    instances, tasks, records = await _center_counts(db, "supplier_claim", cid)
    assert instances == 1 and tasks == 1 and records == 1  # 实例 + L1 任务（qa_pm）+ 旧日志导入

    await migrate_main()
    assert await _center_counts(db, "supplier_claim", cid) == (instances, tasks, records)  # 幂等

    r = await client.get("/api/v1/approvals/pending", headers=pm)
    assert any(it["id"] == cid and it["can_act"] for it in r.json()["data"]["items"])  # 在途恢复
    r = await client.get(f"/api/v1/approvals/items/supplier_claim/{cid}", headers=pm)
    assert any(lg["action"] == "submit" for lg in r.json()["data"]["logs"])  # 历史可查
