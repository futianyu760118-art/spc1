"""审批中心 P2 - 业务接入（只读 SQL 注册 / 测试取数 / 聚合 / 提醒）集成测试。

数据源直接用测试库自身的 supplier_claim 表（不新造业务表），SQL 业务的 id 即索赔单主键。
SQL 业务只聚合与跳转：不支持中心内审批，但节点权限过滤与超时提醒照常。
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


def sql_with_node(label: str) -> str:
    return (
        "SELECT id, claim_no AS no, supplier_name AS title, applicant, "
        f"submitted_at, '{label}' AS current_node FROM supplier_claim"
    )


async def register(client, headers, **overrides):
    return await client.post("/api/v1/approvals/businesses", json=business_payload(**overrides), headers=headers)


async def save_chain(client, headers, nodes, is_active=True):
    return await client.put(f"/api/v1/approvals/configs/{BIZ_TYPE}",
                            json={"nodes": nodes, "is_active": is_active}, headers=headers)


async def _reset_business_state():
    """清空 SQL 业务注册表与用例写入的审批链配置，并同步进程内 provider 注册表。"""
    from app.core.database import AsyncSessionLocal, engine
    from app.services.common.approval_sql_provider import sync_sql_providers

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE approval_business RESTART IDENTITY CASCADE"))
        await conn.execute(text("DELETE FROM approval_config WHERE biz_type = :bt"), {"bt": BIZ_TYPE})
    async with AsyncSessionLocal() as session:
        await sync_sql_providers(session)


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
    """5) 聚合生效：admin 待办出现 SQL 业务条目，can_act=False 且深链按模板渲染。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500, submit=True)
    await create(client, h_q, 600, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0

    data = (await client.get("/api/v1/approvals/pending",
                             params={"biz_type": BIZ_TYPE}, headers=h_admin)).json()["data"]
    assert data["total"] == 2
    item = next(x for x in data["items"] if x["id"] == a["id"])
    assert item["biz_name"] == BIZ_NAME
    assert item["no"] == a["claim_no"] and item["title"] == a["supplier_name"]
    assert item["can_act"] is False and item["status"] == "pending"
    assert item["deep_link"] == f"/quality/supplier-claims/{a['claim_no']}"


async def test_pending_node_permission_filters_sql_business(client):
    """6) 节点权限：非当前节点角色看不到该 SQL 业务条目（PM 看不到「财务结算」行）。"""
    h_admin, h_q, h_pm, h_fin = (
        await login(client, ADMIN), await login(client, Q), await login(client, PM), await login(client, FIN))
    await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin, sql_text=sql_with_node("财务结算"))).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0

    pm_items = (await client.get("/api/v1/approvals/pending",
                                 params={"biz_type": BIZ_TYPE}, headers=h_pm)).json()["data"]["items"]
    assert pm_items == []
    fin_items = (await client.get("/api/v1/approvals/pending",
                                  params={"biz_type": BIZ_TYPE}, headers=h_fin)).json()["data"]["items"]
    assert len(fin_items) == 1 and fin_items[0]["current_node"] == "财务结算"


async def test_disable_and_reenable_sql_business(client):
    """7) 停用后待办消失，重新启用后恢复。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0

    async def pending_count():
        r = await client.get("/api/v1/approvals/pending", params={"biz_type": BIZ_TYPE}, headers=h_admin)
        return len(r.json()["data"]["items"])

    assert await pending_count() == 1

    body = (await client.put(f"/api/v1/approvals/businesses/{BIZ_TYPE}",
                             json=business_payload(is_active=False), headers=h_admin)).json()
    assert body["code"] == 0 and body["data"]["is_active"] is False
    assert await pending_count() == 0

    body = (await client.put(f"/api/v1/approvals/businesses/{BIZ_TYPE}",
                             json=business_payload(is_active=True), headers=h_admin)).json()
    assert body["code"] == 0 and body["data"]["is_active"] is True
    assert await pending_count() == 1


async def test_sql_business_preview_shape(client):
    """8) 抽屉预览：映射字段（中文 label）+ 按链节点推算进度（当前节点 state=current）。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0

    body = (await client.get(f"/api/v1/approvals/items/{BIZ_TYPE}/{a['id']}", headers=h_admin)).json()
    assert body["code"] == 0, body
    data = body["data"]
    assert {"单号", "标题", "申请人", "提交时间", "当前节点"} <= {f["label"] for f in data["fields"]}
    assert data["can_act"] is False
    assert data["deep_link"] == f"/quality/supplier-claims/{a['claim_no']}"
    assert data["progress"][0]["state"] == "current"
    assert data["progress"][1]["state"] == "todo"
    assert "业务系统" in data["action_hint"]


async def test_sql_business_actions_rejected_in_center(client):
    """9) 动作被拒：SQL 业务不支持在审批中心内审批。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0

    body = (await client.post(f"/api/v1/approvals/items/{BIZ_TYPE}/{a['id']}/approve",
                              json={}, headers=h_admin)).json()
    assert body["code"] == 1 and "不支持在审批中心内审批" in body["message"]


async def test_businesses_endpoints_require_permission(client):
    """10) 无 approval.business 权限的角色访问业务接入端点 → 403。"""
    h_pm = await login(client, PM)
    assert (await client.get("/api/v1/approvals/businesses", headers=h_pm)).status_code == 403
    assert (await client.post("/api/v1/approvals/businesses/test-sql",
                              json={"sql_text": SQL_TEXT}, headers=h_pm)).status_code == 403


async def test_timeout_reminder_targets_sql_business_and_stops_when_disabled(client, db):
    """11) 超时提醒：SQL 业务条目带链节点角色解析出的 approver_user_ids，停用后不再命中。"""
    from datetime import datetime, timedelta

    from app.core.database import engine
    from app.services.scheduler.approval_timeout_reminder import ApprovalTimeoutReminderScheduler

    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, [
        {"seq": 1, "label": "索赔部门意见", "role": "purchase_manager", "timeout_hours": 1},
    ])).json()["code"] == 0
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE supplier_claim SET submitted_at = :ts WHERE id = :eid"),
                           {"ts": datetime.now() - timedelta(hours=3), "eid": a["id"]})

    scheduler = ApprovalTimeoutReminderScheduler()
    targets = [t for t in await scheduler._collect_targets(db) if t["biz_type"] == BIZ_TYPE]
    assert len(targets) == 1
    assert targets[0]["approver_user_ids"]
    assert targets[0]["wait_level"] == "overdue" and targets[0]["timeout_hours"] == 1

    assert (await client.put(f"/api/v1/approvals/businesses/{BIZ_TYPE}",
                             json=business_payload(is_active=False), headers=h_admin)).json()["code"] == 0
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
    """历史坏配置（直接入库绕过校验）也不能拖垮全员待办：该业务降级为空，其它业务照常。"""
    h_admin, h_q, h_pm = await login(client, ADMIN), await login(client, Q), await login(client, PM)
    await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, CHAIN)).json()["code"] == 0

    from app.core.database import AsyncSessionLocal, engine
    from app.services.common.approval_sql_provider import sync_sql_providers

    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE approval_business SET sql_text = 'SELECT 1 FROM table_that_does_not_exist' WHERE biz_type = :bt"
        ), {"bt": BIZ_TYPE})
    async with AsyncSessionLocal() as session:
        await sync_sql_providers(session)

    r = await client.get("/api/v1/approvals/pending", headers=h_pm)
    assert r.status_code == 200 and r.json()["code"] == 0
    biz_types = {x["biz_type"] for x in r.json()["data"]["items"]}
    assert "supplier_claim" in biz_types and BIZ_TYPE not in biz_types


BROKEN_BIZ = "pytest_broken_first"
BROKEN_SQL = "SELECT 1 FROM table_that_does_not_exist"


async def _insert_broken_business():
    """直插一条坏 SQL 业务（模拟历史坏配置：曾经健康、源表后来失效，绕过保存校验）。"""
    from app.core.database import AsyncSessionLocal, engine
    from app.services.common.approval_sql_provider import sync_sql_providers

    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO approval_business
                (biz_type, biz_name, mode, sql_text, field_mapping_json, condition_fields_json, is_active)
            VALUES (:bt, '坏业务', 'sql', :sql, :fm, '[]', TRUE)
        """), {"bt": BROKEN_BIZ, "sql": BROKEN_SQL, "fm": json.dumps(FIELD_MAPPING)})
    async with AsyncSessionLocal() as session:
        await sync_sql_providers(session)


async def test_broken_sql_before_healthy_business_does_not_hide_it(client, db):
    """坏 SQL 注册顺序靠前时，也不能让后面的健康业务从待办 / 在途数 / 提醒扫描里静默消失（SAVEPOINT 隔离）。"""
    from datetime import datetime, timedelta

    from app.core.database import engine

    h_admin, h_q, h_pm = await login(client, ADMIN), await login(client, Q), await login(client, PM)
    claim = await create(client, h_q, 500, submit=True)
    await _insert_broken_business()  # id 更小 → provider 注册在前，先被执行
    assert (await register(client, h_admin)).json()["code"] == 0
    assert (await save_chain(client, h_admin, [
        {"seq": 1, "label": "索赔部门意见", "role": "purchase_manager", "timeout_hours": 1},
    ])).json()["code"] == 0
    async with engine.begin() as conn:  # 造一条超时待办，让提醒扫描有目标
        await conn.execute(text("UPDATE supplier_claim SET submitted_at = :ts WHERE id = :eid"),
                           {"ts": datetime.now() - timedelta(hours=3), "eid": claim["id"]})

    r = await client.get("/api/v1/approvals/pending", headers=h_pm)
    assert r.status_code == 200 and r.json()["code"] == 0
    assert BIZ_TYPE in {x["biz_type"] for x in r.json()["data"]["items"]}, "坏业务在前时健康业务不得被跳过"

    r = await client.get("/api/v1/approvals/businesses", headers=h_admin)
    healthy = next(x for x in r.json()["data"]["items"] if x["biz_type"] == BIZ_TYPE)
    assert healthy["pending_count"] == 1

    # 超时提醒扫描同样不能被坏业务阻断（调度器侧也有 SAVEPOINT 隔离）
    from app.services.scheduler.approval_timeout_reminder import ApprovalTimeoutReminderScheduler

    scheduler = ApprovalTimeoutReminderScheduler()
    collected = await scheduler._collect_targets(db)
    assert BIZ_TYPE in {t["biz_type"] for t in collected}


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
    """provider_mode 筛选：builtin 只留代码 Provider 业务，sql 只留 SQL 接入业务；stats 仍为全量口径。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0

    r = await client.get("/api/v1/approvals/pending", params={"provider_mode": "builtin"}, headers=h_admin)
    data = r.json()["data"]
    assert {x["biz_type"] for x in data["items"]} == {"supplier_claim"}
    assert data["stats"]["by_biz"].get(BIZ_TYPE) == 1  # stats 不随接入方式筛选收缩

    r = await client.get("/api/v1/approvals/pending", params={"provider_mode": "sql"}, headers=h_admin)
    data = r.json()["data"]
    assert {x["biz_type"] for x in data["items"]} == {BIZ_TYPE}

    r = await client.get("/api/v1/approvals/pending", headers=h_admin)
    assert {x["biz_type"] for x in r.json()["data"]["items"]} == {"supplier_claim", BIZ_TYPE}


async def test_sql_business_recall_rejected_in_center(client):
    """SQL 接入业务无撤回能力：统一撤回端点返回业务错误。"""
    h_admin, h_q = await login(client, ADMIN), await login(client, Q)
    a = await create(client, h_q, 500, submit=True)
    assert (await register(client, h_admin)).json()["code"] == 0
    body = (await client.post(f"/api/v1/approvals/items/{BIZ_TYPE}/{a['id']}/recall",
                              json={}, headers=h_admin)).json()
    assert body["code"] == 1 and "不支持在审批中心内" in body["message"]
