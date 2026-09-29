"""审批中心 P2 - 业务接入（只读 SQL 注册 / 测试取数 / 提交 / 审批 / 回写 / 提醒）集成测试。

数据源直接用测试库自身的 supplier_claim 表（不新造业务表），SQL 业务的 id 即索赔单主键。
声明式业务经 POST /approvals/instances 提交（摘要由取数 SQL 生成），可在中心内审批并按
配置回写业务表；待办查中心三表，与取数 SQL 天然隔离。
"""

import json

import pytest_asyncio
from sqlalchemy import text

from tests.conftest import login
from tests.integration._helpers import FIN, PM, Q, create

ADMIN = "admin"
BIZ_TYPE = "pytest_claim_board"
BIZ_NAME = "索赔看板业务"

SQL_TEXT = (
    "SELECT id, claim_no AS no, supplier_name AS title, applicant, "
    "submitted_at, '索赔部门意见' AS current_node FROM supplier_claim"
)
FIELD_MAPPING = {
    "id": "id", "no": "no", "title": "title", "applicant": "applicant",
    "submitted_at": "submitted_at", "current_node": "current_node",
}
CONDITION_FIELDS = [{"value": "claim_amount", "label": "索赔金额"}]
DEEP_LINK = "/quality/supplier-claims/{no}"
CHAIN = [
    {"seq": 1, "label": "索赔部门意见", "role": "purchase_manager"},
    {"seq": 2, "label": "财务结算", "role": "finance"},
]


def business_payload(**overrides) -> dict:
    data = {
        "biz_type": BIZ_TYPE,
        "biz_name": BIZ_NAME,
        "sql_text": SQL_TEXT,
        "field_mapping": dict(FIELD_MAPPING),
        "condition_fields": list(CONDITION_FIELDS),
        "deep_link_template": DEEP_LINK,
        "description": "pytest SQL 接入业务",
    }
    data.update(overrides)
    return data


async def register(client, headers, **overrides):
    return await client.post("/api/v1/approvals/businesses", json=business_payload(**overrides), headers=headers)


async def save_chain(client, headers, nodes, is_active=True):
    return await client.put(f"/api/v1/approvals/configs/{BIZ_TYPE}",
                            json={"nodes": nodes, "is_active": is_active}, headers=headers)


async def submit_instance(client, headers, biz_id):
    """声明式业务经中心提交审批实例（摘要由取数 SQL 生成）。"""
    return await client.post("/api/v1/approvals/instances",
                             json={"biz_type": BIZ_TYPE, "biz_id": biz_id}, headers=headers)


async def _reset_business_state():
    """清空 SQL 业务注册表与本文件造数写入的审批链配置，避免污染其它用例。"""
    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE approval_business RESTART IDENTITY CASCADE"))
        await conn.execute(text("DELETE FROM approval_config WHERE biz_type = :bt"), {"bt": BIZ_TYPE})


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _isolated_business_registry(_test_db):
    await _reset_business_state()
    yield
    await _reset_business_state()


async def test_register_sql_business_listed_with_config_fields(client):
    """1) 注册 SQL 业务 → 列表可见（mode=sql / has_sql），编辑所需配置字段随列表返回。"""
    h_admin = await login(client, ADMIN)
    body = (await register(client, h_admin)).json()
    assert body["code"] == 0, body
    assert body["data"]["biz_type"] == BIZ_TYPE

    items = (await client.get("/api/v1/approvals/businesses", headers=h_admin)).json()["data"]["items"]
    hit = next(x for x in items if x["biz_type"] == BIZ_TYPE)
    assert hit["mode"] == "sql" and hit["has_sql"] is True and hit["is_active"] is True
    assert hit["biz_name"] == BIZ_NAME and hit["description"] == "pytest SQL 接入业务"
    assert hit["sql_text"] == SQL_TEXT
    assert hit["field_mapping"] == FIELD_MAPPING
    assert hit["condition_fields"] == CONDITION_FIELDS
    assert hit["deep_link_template"] == DEEP_LINK
    assert hit["pending_count"] == 0 and hit["chain_node_count"] == 0
    assert hit["updated_by"] == ADMIN and hit["updated_at"]

    builtin = next(x for x in items if x["biz_type"] == "supplier_claim")
    assert builtin["mode"] == "builtin" and builtin["has_sql"] is False
    assert builtin["sql_text"] is None and builtin["field_mapping"] == {}
    assert builtin["condition_fields"] == [] and builtin["deep_link_template"] is None


async def test_test_sql_preview_returns_columns_and_limited_rows(client):
    """2) test-sql 预览：返回映射列、行数不超过 5 行、带耗时。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    await create(client, h_q, 500, submit=True)
    await create(client, h_q, 600, submit=True)

    body = (await client.post("/api/v1/approvals/businesses/test-sql",
                              json={"sql_text": SQL_TEXT}, headers=h_admin)).json()
    assert body["code"] == 0, body
    data = body["data"]
    assert {"id", "no", "title", "applicant", "submitted_at", "current_node"} <= set(data["columns"])
    assert len(data["rows"]) == 2 and len(data["rows"]) <= 5
    assert data["elapsed_ms"] >= 0


async def test_test_sql_rejects_write_and_multi_statement(client):
    """3) test-sql 拒绝写操作 / 多语句 / 分号结尾，并给出可读原因。"""
    h_admin = await login(client, ADMIN)
    cases = [
        ("UPDATE supplier_claim SET remarks = 'x'", "只读"),
        ("SELECT 1; SELECT 2", "单条"),
        ("SELECT 1;", "单条"),
    ]
    for sql_text, keyword in cases:
        body = (await client.post("/api/v1/approvals/businesses/test-sql",
                                  json={"sql_text": sql_text}, headers=h_admin)).json()
        assert body["code"] == 1, sql_text
        assert keyword in body["message"], (sql_text, body["message"])


async def test_register_validation_rejects_bad_payload(client):
    """4) 注册校验：缺必需映射 / 非法业务标识 / 与内置业务重名。"""
    h_admin = await login(client, ADMIN)
    broken_mapping = {k: v for k, v in FIELD_MAPPING.items() if k != "id"}
    body = (await register(client, h_admin, field_mapping=broken_mapping)).json()
    assert body["code"] == 1 and "必需" in body["message"]

    for bad_type in ("ClaimBoard", "claim-board", "1claim"):
        body = (await register(client, h_admin, biz_type=bad_type)).json()
        assert body["code"] == 1, bad_type
        assert "业务标识" in body["message"]

    body = (await register(client, h_admin, biz_type="supplier_claim")).json()
    assert body["code"] == 1 and "内置业务" in body["message"]

    assert (await register(client, h_admin)).json()["code"] == 0
    body = (await register(client, h_admin)).json()
    assert body["code"] == 1 and "已注册" in body["message"]


async def test_sql_business_items_aggregate_for_admin(client):
    """5) 聚合生效：声明式业务提交后 admin 待办出现条目（摘要取自取数 SQL），可审批且深链按模板渲染。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500)  # 草稿：不经 builtin 提交，专供声明式业务接管
    b = await create(client, h_q, 600)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0
    for cid in (a["id"], b["id"]):
        r = await submit_instance(client, h_q, cid)
        assert r.json()["code"] == 0, r.text

    data = (await client.get("/api/v1/approvals/pending",
                             params={"biz_type": BIZ_TYPE}, headers=h_admin)).json()["data"]
    assert data["total"] == 2
    item = next(x for x in data["items"] if x["id"] == a["id"])
    assert item["biz_name"] == BIZ_NAME
    assert item["no"] == a["claim_no"] and item["title"] == a["supplier_name"]
    assert item["can_act"] is True and item["status"] == "pending"
    assert item["deep_link"] == f"/quality/supplier-claims/{a['claim_no']}"


async def test_pending_node_permission_filters_sql_business(client):
    """6) 节点权限：任务只展开到链节点角色（PM 持节点1任务可见，财务在节点到达前不可见）。"""
    h_admin, h_q, h_pm, h_fin = (
        await login(client, ADMIN), await login(client, Q), await login(client, PM), await login(client, FIN))
    a = await create(client, h_q, 500)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0
    assert (await submit_instance(client, h_q, a["id"])).json()["code"] == 0

    pm_items = (await client.get("/api/v1/approvals/pending",
                                 params={"biz_type": BIZ_TYPE}, headers=h_pm)).json()["data"]["items"]
    assert len(pm_items) == 1 and pm_items[0]["current_node"] == "索赔部门意见"
    fin_items = (await client.get("/api/v1/approvals/pending",
                                  params={"biz_type": BIZ_TYPE}, headers=h_fin)).json()["data"]["items"]
    assert fin_items == []


async def test_disable_and_reenable_sql_business(client):
    """7) 停用后不再产生新待办（提交被拒），在途待办保留可见；重新启用后恢复可提交。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500)
    b = await create(client, h_q, 600)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0
    assert (await submit_instance(client, h_q, a["id"])).json()["code"] == 0

    async def pending_count():
        r = await client.get("/api/v1/approvals/pending", params={"biz_type": BIZ_TYPE}, headers=h_admin)
        return len(r.json()["data"]["items"])

    assert await pending_count() == 1

    body = (await client.put(f"/api/v1/approvals/businesses/{BIZ_TYPE}",
                             json=business_payload(is_active=False), headers=h_admin)).json()
    assert body["code"] == 0 and body["data"]["is_active"] is False
    assert await pending_count() == 1  # 在途单据按冻结快照继续，待办不消失
    r = await submit_instance(client, h_q, b["id"])
    assert r.json()["code"] == 1 and "停用" in r.json()["message"]

    body = (await client.put(f"/api/v1/approvals/businesses/{BIZ_TYPE}",
                             json=business_payload(is_active=True), headers=h_admin)).json()
    assert body["code"] == 0 and body["data"]["is_active"] is True
    assert (await submit_instance(client, h_q, b["id"])).json()["code"] == 0
    assert await pending_count() == 2


async def test_sql_business_preview_shape(client):
    """8) 详情页：映射字段（中文 label）+ 按链快照推算进度（当前节点 state=current），可审批。"""
    from app.core.database import engine

    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500)
    async with engine.begin() as conn:  # 模拟源系统自带提交时间（草稿索赔单该列为空）
        await conn.execute(text("UPDATE supplier_claim SET submitted_at = NOW() WHERE id = :i"),
                           {"i": a["id"]})
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0
    assert (await submit_instance(client, h_q, a["id"])).json()["code"] == 0

    body = (await client.get(f"/api/v1/approvals/items/{BIZ_TYPE}/{a['id']}", headers=h_admin)).json()
    assert body["code"] == 0, body
    data = body["data"]
    assert {"单号", "标题", "申请人", "提交时间", "当前节点"} <= {f["label"] for f in data["fields"]}
    assert data["can_act"] is True
    assert data["deep_link"] == f"/quality/supplier-claims/{a['claim_no']}"
    assert data["progress"][0]["state"] == "current"
    assert data["progress"][1]["state"] == "todo"


async def test_sql_business_approve_and_writeback_in_center(client, db):
    """9) 声明式业务可在中心内审批：单级链通过后归档，并按回写配置同步业务表状态列。"""
    h_admin, h_q, h_pm = await login(client, ADMIN), await login(client, Q), await login(client, PM)
    a = await create(client, h_q, 500)  # 草稿交由声明式业务接管，回写 approval_status 不干扰 builtin 实例
    writeback = {"table": "supplier_claim", "id_column": "id", "status_column": "approval_status",
                 "status_map": {"pending": "pending", "approved": "approved",
                                "rejected": "rejected", "recalled": "draft"}}
    assert (await register(client, h_admin, writeback=writeback)).json()["code"] == 0
    assert (await save_chain(client, h_admin, [
        {"seq": 1, "label": "索赔部门意见", "role": "purchase_manager"},
    ])).json()["code"] == 0
    assert (await submit_instance(client, h_q, a["id"])).json()["code"] == 0
    status = (await db.execute(text(
        "SELECT approval_status FROM supplier_claim WHERE id = :i"), {"i": a["id"]})).scalar()
    assert status == "pending"  # 提交即回写

    body = (await client.post(f"/api/v1/approvals/items/{BIZ_TYPE}/{a['id']}/approve",
                              json={}, headers=h_pm)).json()
    assert body["code"] == 0 and body["data"]["finished"] is True, body
    status = (await db.execute(text(
        "SELECT approval_status FROM supplier_claim WHERE id = :i"), {"i": a["id"]})).scalar()
    assert status == "approved"  # 回写映射生效


async def test_businesses_endpoints_require_permission(client):
    """10) 无 approval.business 权限的角色访问业务接入端点 → 403。"""
    h_pm = await login(client, PM)
    assert (await client.get("/api/v1/approvals/businesses", headers=h_pm)).status_code == 403
    assert (await client.post("/api/v1/approvals/businesses/test-sql",
                              json={"sql_text": SQL_TEXT}, headers=h_pm)).status_code == 403


async def test_timeout_reminder_targets_sql_business_and_stops_when_chain_disabled(client, db):
    """11) 超时提醒：中心实例超时后命中当前节点审批人；停用审批链后不再提醒。"""
    from datetime import datetime, timedelta

    from app.core.database import engine
    from app.services.scheduler.approval_timeout_reminder import ApprovalTimeoutReminderScheduler

    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, [
        {"seq": 1, "label": "索赔部门意见", "role": "purchase_manager", "timeout_hours": 1},
    ])).json()["code"] == 0
    assert (await submit_instance(client, h_q, a["id"])).json()["code"] == 0
    async with engine.begin() as conn:  # 提醒扫描数据源在中心实例表，直改业务表不再生效
        await conn.execute(text(
            "UPDATE approval_instance SET submitted_at = :ts WHERE biz_type = :bt AND biz_id = :eid"),
            {"ts": datetime.now() - timedelta(hours=3), "bt": BIZ_TYPE, "eid": a["id"]})

    scheduler = ApprovalTimeoutReminderScheduler()
    targets = [t for t in await scheduler._collect_targets(db) if t["biz_type"] == BIZ_TYPE]
    assert len(targets) == 1
    assert targets[0]["approver_user_ids"]
    assert targets[0]["wait_level"] == "overdue" and targets[0]["timeout_hours"] == 1

    assert (await save_chain(client, h_admin, [
        {"seq": 1, "label": "索赔部门意见", "role": "purchase_manager", "timeout_hours": 1},
    ], is_active=False)).json()["code"] == 0
    assert [t for t in await scheduler._collect_targets(db) if t["biz_type"] == BIZ_TYPE] == []


async def test_register_rejects_unexecutable_sql_and_bad_id_mapping(client):
    """保存前实跑取数：坏 SQL 与「id 映射到非数字列」都必须被拒，避免运行期 500 / 预览失效。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    await create(client, h_q, 500)  # 造一行数据，id 类型校验才会真正跑到

    broken = await register(client, h_admin,
                            sql_text="SELECT id, no FROM table_that_does_not_exist")
    assert broken.json()["code"] == 1 and "SQL 执行失败" in broken.json()["message"]

    bad_column = await register(client, h_admin,
                               field_mapping={**FIELD_MAPPING, "title": "no_such_column"})
    assert bad_column.json()["code"] == 1 and "不在取数结果中" in bad_column.json()["message"]

    bad_id = await register(client, h_admin,
                            sql_text="SELECT claim_no AS id, claim_no AS no, supplier_name AS title, applicant, "
                                     "submitted_at, '索赔部门意见' AS current_node FROM supplier_claim")
    assert bad_id.json()["code"] == 1 and "数字主键" in bad_id.json()["message"]

    # 映射含未知字段（拼写错误）也应被拒
    typo = await register(client, h_admin, field_mapping={**FIELD_MAPPING, "titel": "title"})
    assert typo.json()["code"] == 1 and "未知字段" in typo.json()["message"]


async def test_broken_sql_in_table_does_not_break_pending(client):
    """历史坏配置（直接入库绕过校验）也不能拖垮全员待办：待办查中心实例表，不执行取数 SQL。"""
    h_admin, h_q, h_pm = await login(client, ADMIN), await login(client, Q), await login(client, PM)
    await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0

    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE approval_business SET sql_text = 'SELECT 1 FROM table_that_does_not_exist' WHERE biz_type = :bt"
        ), {"bt": BIZ_TYPE})

    r = await client.get("/api/v1/approvals/pending", headers=h_pm)
    assert r.status_code == 200 and r.json()["code"] == 0
    biz_types = {x["biz_type"] for x in r.json()["data"]["items"]}
    assert "supplier_claim" in biz_types and BIZ_TYPE not in biz_types


BROKEN_BIZ = "pytest_broken_first"
BROKEN_SQL = "SELECT 1 FROM table_that_does_not_exist"


async def _insert_broken_business():
    """直插一条坏 SQL 业务（模拟历史坏配置：曾经健康、源表后来失效，绕过保存校验）。"""
    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO approval_business
                (biz_type, biz_name, mode, sql_text, field_mapping_json, condition_fields_json,
                 writeback_json, is_active)
            VALUES (:bt, '坏业务', 'sql', :sql, :fm, '[]', '{}', TRUE)
        """), {"bt": BROKEN_BIZ, "sql": BROKEN_SQL, "fm": json.dumps(FIELD_MAPPING)})


async def test_broken_sql_before_healthy_business_does_not_hide_it(client):
    """坏 SQL 业务注册在前也不影响他人：待办查中心实例表、在途数查实例计数，均不执行取数 SQL。"""
    h_admin, h_q, h_pm = await login(client, ADMIN), await login(client, Q), await login(client, PM)
    a = await create(client, h_q, 500)
    await _insert_broken_business()  # id 更小 → 业务清单排在健康业务前
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0
    assert (await submit_instance(client, h_q, a["id"])).json()["code"] == 0

    r = await client.get("/api/v1/approvals/pending", headers=h_pm)
    assert r.status_code == 200 and r.json()["code"] == 0
    assert BIZ_TYPE in {x["biz_type"] for x in r.json()["data"]["items"]}, "坏业务在前时健康业务不得被跳过"

    r = await client.get("/api/v1/approvals/businesses", headers=h_admin)
    assert r.json()["code"] == 0, r.text
    healthy = next(x for x in r.json()["data"]["items"] if x["biz_type"] == BIZ_TYPE)
    assert healthy["pending_count"] == 1


async def test_broken_business_can_be_disabled(client):
    """源表失效的坏业务必须能被停用（只改启停时不重跑取数，管理员保留自救手段）。"""
    h_admin = await login(client, ADMIN)
    await _insert_broken_business()
    r = await client.put(f"/api/v1/approvals/businesses/{BROKEN_BIZ}",
                         json={**business_payload(biz_type=BROKEN_BIZ, sql_text=BROKEN_SQL), "is_active": False},
                         headers=h_admin)
    assert r.json()["code"] == 0 and r.json()["data"]["is_active"] is False
    r = await client.get("/api/v1/approvals/businesses", headers=h_admin)
    row = next(x for x in r.json()["data"]["items"] if x["biz_type"] == BROKEN_BIZ)
    assert row["is_active"] is False


async def test_pending_provider_mode_filter(client):
    """provider_mode 筛选：builtin 只留代码 Adapter 业务，sql 只留声明式业务；stats 仍为全量口径。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    await create(client, h_q, 500, submit=True)  # builtin：索赔单经业务端提交
    a = await create(client, h_q, 600)           # 声明式：草稿经中心提交
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0
    assert (await submit_instance(client, h_q, a["id"])).json()["code"] == 0

    r = await client.get("/api/v1/approvals/pending", params={"provider_mode": "builtin"}, headers=h_admin)
    data = r.json()["data"]
    assert {x["biz_type"] for x in data["items"]} == {"supplier_claim"}
    assert data["stats"]["by_biz"].get(BIZ_TYPE) == 1  # stats 不随接入方式筛选收缩

    r = await client.get("/api/v1/approvals/pending", params={"provider_mode": "sql"}, headers=h_admin)
    data = r.json()["data"]
    assert {x["biz_type"] for x in data["items"]} == {BIZ_TYPE}

    r = await client.get("/api/v1/approvals/pending", headers=h_admin)
    assert {x["biz_type"] for x in r.json()["data"]["items"]} == {"supplier_claim", BIZ_TYPE}


async def test_sql_business_recall_by_applicant(client):
    """声明式业务支持撤回：发起人页内撤回 → 实例 recalled，「我发起的」可见且不可再撤。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0
    assert (await submit_instance(client, h_q, a["id"])).json()["code"] == 0

    body = (await client.post(f"/api/v1/approvals/items/{BIZ_TYPE}/{a['id']}/recall",
                              json={}, headers=h_q)).json()
    assert body["code"] == 0 and "撤回" in body["message"], body

    r = await client.get("/api/v1/approvals/submitted", params={"biz_type": BIZ_TYPE}, headers=h_q)
    mine = next(x for x in r.json()["data"]["items"] if x["id"] == a["id"])
    assert mine["status"] == "recalled" and mine["can_recall"] is False
