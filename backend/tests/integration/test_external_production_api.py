"""生产协同对外接口（production.* 5 端点）集成回归测试。

独立测试库 spc_test + ASGI 内存客户端 + HMAC 签名（rate_limit=0 绕过 Redis）。
覆盖：鉴权 401/403、工单状态映射与 DB 层过滤、工序/关联/报工锚点校验、
双源关联、产能聚合（含周日口径）、空过滤仍携带 data_as_of、request_id 回显、
任务单订单号经 sale_order.erp_id 解析（输出与过滤）、
工序/报工/产能快照基线时效（旧数据不判过期，空表回退导入/同步时间）。
"""

from datetime import date, datetime

import pytest_asyncio

from tests.integration.test_external_quality_api import signed_get

WO_LIST = "/api/v1/external/production/work-orders/list"
OPS_LIST = "/api/v1/external/production/operations/list"
LINKS_LIST = "/api/v1/external/production/order-links/list"
REPORTS_LIST = "/api/v1/external/production/reports/list"
CAPACITY_LIST = "/api/v1/external/production/capacity/list"


@pytest_asyncio.fixture(loop_scope="session")
async def prod_seeded(external_keys, db):
    """3 任务单 + 2 工序进度 + 1 排产快照 + 2 ERP 日报 + 3 产能槽 + 1 基础条件。"""
    from app.models.production.base_condition import ProductionBaseCondition
    from app.models.production.capacity_slot import CapacitySlot
    from app.models.production.order_schedule_snapshot import ProductionOrderScheduleSnapshot
    from app.models.production.process_progress import ProcessProgress
    from app.models.production.production_daily_report import ProductionDailyReport
    from app.models.production.production_task_order import ProductionTaskOrder

    db.add_all([
        ProductionTaskOrder(task_no="WO-2609-001", task_id=101, workshop="车间A",
                            material_code="P-100", material_name="产品A",
                            planned_start_date=date(2026, 9, 10), planned_end_date=date(2026, 9, 18),
                            actual_start_date=date(2026, 9, 11), actual_end_date=date(2026, 9, 18),
                            task_qty=100, actual_qty=100, repair_qty=2,
                            sale_order_no="SO-2609-099", sale_order_id=9001, bom_id=101,
                            start_flag=1, is_closed=1, audit_status=1),
        ProductionTaskOrder(task_no="WO-2609-002", task_id=102, workshop="车间B",
                            material_code="P-100", material_name="产品A",
                            planned_start_date=date(2026, 9, 15), planned_end_date=date(2026, 9, 20),
                            actual_start_date=date(2026, 9, 16),
                            task_qty=500, actual_qty=70,
                            sale_order_no="SO-2609-001", sale_order_id=9002, bom_id=101,
                            start_flag=1, is_closed=0, audit_status=1),
        ProductionTaskOrder(task_no="WO-2609-003", task_id=103, workshop="车间C",
                            material_code="P-200", task_qty=50),
        ProcessProgress(process_type="组装", order_no="SO-2609-001", line_no="1",
                        product_code="P-100", planned_qty=500, qty=70,
                        plan_date=date(2026, 9, 22), status="in_progress"),
        ProcessProgress(process_type="包装", order_no="SO-2609-001", line_no="1",
                        product_code="P-100", planned_qty=500,
                        plan_date=date(2026, 9, 23), status="pending"),
        ProductionOrderScheduleSnapshot(order_no="SO-2609-001", line_no="1",
                                        sale_order_line_id=501, product_code="P-100",
                                        order_qty=500, promised_date=date(2026, 9, 28)),
        ProductionDailyReport(oa_id="DR-001", oa_detail_id=1, report_date=date(2026, 9, 21),
                              sale_order_no="SO-2609-001", production_order_no="WO-2609-002",
                              material_code="P-100", process="组装", completed_qty=30,
                              workshop="车间B"),
        ProductionDailyReport(oa_id="DR-002", oa_detail_id=2, report_date=date(2026, 9, 22),
                              sale_order_no="SO-2609-001", production_order_no="WO-2609-002",
                              material_code="P-100", process="组装", completed_qty=40,
                              workshop="车间B"),
        CapacitySlot(department="车间A", schedule_bucket="assembly",
                     slot_date=datetime(2026, 9, 23), hours=4, order_no="SO-2609-001"),
        CapacitySlot(department="车间A", schedule_bucket="assembly",
                     slot_date=datetime(2026, 9, 23), hours=4.5, order_no="SO-2609-001"),
        CapacitySlot(department="车间A", schedule_bucket="assembly",
                     slot_date=datetime(2026, 9, 27), hours=2, order_no="SO-2609-001"),
        ProductionBaseCondition(schedule_bucket="assembly", bucket_label="组装段",
                                default_manpower=10, daily_work_hours=8, include_sunday=False),
    ])
    await db.commit()
    return {"order_no": "SO-2609-001", "work_order_no": "WO-2609-002"}


async def test_missing_auth_401(ext_client):
    r = await ext_client.get(WO_LIST)
    assert r.status_code == 401


async def test_bad_signature_403(ext_client, external_keys):
    import time

    from tests._common_external import build_headers, generate_signature

    key = external_keys["production"]
    timestamp = int(time.time())
    _, signature = generate_signature(timestamp, key["app_key"], "wrong_secret", "production.work_orders.list", "")
    r = await ext_client.get(WO_LIST, headers=build_headers(key["app_key"], signature, timestamp))
    assert r.status_code == 403


async def test_endpoint_not_authorized_403(ext_client, external_keys):
    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", external_keys["orders"])
    assert r.status_code == 403


async def test_work_orders_mapping_and_status(ext_client, external_keys, prod_seeded):
    key = external_keys["production"]
    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"page_size": 10})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 3
    by_no = {it["work_order_no"]: it for it in data["items"]}
    assert by_no["WO-2609-001"]["status"] == "completed"
    assert by_no["WO-2609-001"]["status_raw"] == "closed"
    assert by_no["WO-2609-002"]["status"] == "in_progress"
    assert by_no["WO-2609-002"]["status_raw"] == "started"
    assert by_no["WO-2609-003"]["status"] == "unknown"
    assert by_no["WO-2609-003"]["status_raw"] is None
    wo1 = by_no["WO-2609-001"]
    assert wo1["planned_qty"] == 100.0 and wo1["completed_qty"] == 100.0 and wo1["repair_qty"] == 2.0
    assert wo1["bom_id"] == "101" and wo1["source_system"] == "oa"
    for field in ("uom", "good_qty", "scrap_qty", "received_qty", "estimated_finish_at",
                  "schedule_version", "owner", "blocking", "blocking_reason", "bom_version"):
        assert wo1[field] is None


async def test_work_orders_filters(ext_client, external_keys, prod_seeded):
    key = external_keys["production"]

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"order_no": "SO-2609-001"})
    assert r.json()["data"]["total"] == 1

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"status": "completed"})
    assert r.json()["data"]["total"] == 1

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"status": "in_progress"})
    assert r.json()["data"]["total"] == 1

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"status": "unknown"})
    assert r.json()["data"]["total"] == 1

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"workshop": "车间B"})
    assert r.json()["data"]["total"] == 1

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"planned_end_end": "2026-09-19"})
    assert r.json()["data"]["total"] == 1  # WO-001（09-18）；WO-002 是 09-20 不含

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"planned_end_start": "2026-09-19"})
    assert r.json()["data"]["total"] == 1

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key, {"planned_end_end": "2026-09-20"})
    assert r.json()["data"]["total"] == 2

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key,
                         {"updated_after": "2999-01-01T00:00:00"})
    assert r.json()["data"]["total"] == 0


async def test_work_order_sale_order_resolution(ext_client, external_keys, db):
    """任务单不冗余订单号（sale_order_no 生产库全空）：经 sale_order.erp_id 解析并支持 order_no 过滤。"""
    from app.models.order.sale_order import SaleOrder
    from app.models.production.production_task_order import ProductionTaskOrder

    db.add_all([
        SaleOrder(order_no="HJ202609-0023-0213", line_no="10", erp_id=5919, status="open"),
        ProductionTaskOrder(task_no="WORK110790", task_id=110790, workshop="车间A",
                            material_code="P-100", task_qty=10, sale_order_id=5919),
    ])
    await db.commit()

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list",
                         external_keys["production"], {"work_order_no": "WORK110790"})
    item = r.json()["data"]["items"][0]
    assert item["order_no"] == "HJ202609-0023-0213"
    assert item["sale_order_id"] == 5919

    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list",
                         external_keys["production"], {"order_no": "HJ202609-0023-0213"})
    data = r.json()["data"]
    assert data["total"] == 1 and data["items"][0]["work_order_no"] == "WORK110790"

    r = await signed_get(ext_client, LINKS_LIST, "production.order_links.list",
                         external_keys["production"], {"work_order_no": "WORK110790"})
    links = r.json()["data"]["items"]
    assert len(links) == 1 and links[0]["link_type"] == "production_task"
    assert links[0]["order_no"] == "HJ202609-0023-0213"

    r = await signed_get(ext_client, LINKS_LIST, "production.order_links.list",
                         external_keys["production"], {"order_no": "HJ202609-0023-0213"})
    links = r.json()["data"]["items"]
    assert len(links) == 1 and links[0]["work_order_no"] == "WORK110790"


async def test_work_orders_freshness_and_echo(ext_client, external_keys, prod_seeded):
    key = external_keys["production"]
    r = await signed_get(ext_client, WO_LIST, "production.work_orders.list", key,
                         {"updated_after": "2999-01-01T00:00:00", "request_id": "prod-001"})
    data = r.json()["data"]
    assert data["items"] == [] and data["total"] == 0
    # data_as_of 为源表全表口径：过滤结果为空仍携带真实刷新时间
    assert data["data_as_of"] is not None
    assert data["data_confidence"] in ("high", "medium")
    assert data["stale"] is False
    assert data["request_id"] == "prod-001"


async def test_empty_table_freshness_contract(ext_client, external_keys):
    """源表无任何行：工序/报工回退真实刷新时间（导入/同步），产能无回退源则 code=503 结构化错误。"""
    key = external_keys["production"]

    r = await signed_get(ext_client, OPS_LIST, "production.operations.list", key,
                         {"order_no": "SO-NOT-EXIST", "request_id": "prod-empty-ops"})
    data = r.json()["data"]
    assert data["items"] == [] and data["total"] == 0
    # 表为空且无生产任务单同步配置 → 回退 audit_log 的 process_progress 最近导入时间；快照基线口径
    assert data["data_as_of"] == "2026-09-20T10:00:00"
    assert data["data_confidence"] == "medium"
    assert data["stale"] is False
    assert data["request_id"] == "prod-empty-ops"

    r = await signed_get(ext_client, REPORTS_LIST, "production.reports.list", key,
                         {"work_order_no": "WO-NOT-EXIST"})
    data = r.json()["data"]
    assert data["items"] == [] and data["total"] == 0
    # 表为空 → 回退 sync_sql_config 的 production_daily_reports 最近成功同步时间
    assert data["data_as_of"] == "2026-08-06T15:44:03"
    assert data["data_confidence"] == "medium"
    assert data["stale"] is False

    r = await signed_get(ext_client, CAPACITY_LIST, "production.capacity.list", key,
                         {"date_start": "2026-09-23", "date_end": "2026-09-23"})
    assert r.status_code == 200
    body = r.json()
    # 产能无同步/导入来源，全空时返回结构化错误，不返回可被误用的空数据
    assert body["code"] == 503
    assert body["data"] is None
    assert "数据源不可用" in body["message"]


async def test_operations_sync_fallback_freshness(ext_client, external_keys, db):
    """工序表全空且无导入记录时，回退生产任务单同步时间：数据源已成功同步 → 真实时效 + stale=false。"""
    from sqlalchemy import delete, text

    from app.models.basicdata.sync_sql_config import SyncSqlConfig

    await db.execute(text("""
        INSERT INTO sync_sql_config
            (sync_type, description, sql_text, sync_interval, sync_strategy,
             sync_priority, sync_enabled, is_active, last_sync_time)
        VALUES ('production_task_orders', 'pytest 工序时效回退种子', 'SELECT 1', '1h', 'full',
                5, TRUE, TRUE, :t)
        ON CONFLICT (sync_type) DO UPDATE SET last_sync_time = EXCLUDED.last_sync_time
    """), {"t": datetime(2026, 8, 10, 9, 0, 0)})
    await db.commit()
    try:
        r = await signed_get(ext_client, OPS_LIST, "production.operations.list",
                             external_keys["production"], {"order_no": "SO-NOT-EXIST"})
        data = r.json()["data"]
        assert data["items"] == [] and data["total"] == 0
        assert data["data_as_of"] == "2026-08-10T09:00:00"
        assert data["data_confidence"] == "medium"
        assert data["stale"] is False
    finally:
        await db.execute(delete(SyncSqlConfig).where(
            SyncSqlConfig.sync_type == "production_task_orders"))
        await db.commit()


async def test_operations_anchor_required_422(ext_client, external_keys):
    r = await signed_get(ext_client, OPS_LIST, "production.operations.list", external_keys["production"])
    assert r.status_code == 422


async def test_operations_list(ext_client, external_keys, prod_seeded):
    key = external_keys["production"]

    r = await signed_get(ext_client, OPS_LIST, "production.operations.list", key, {"order_no": "SO-2609-001"})
    data = r.json()["data"]
    assert data["total"] == 2
    by_code = {it["operation_code"]: it for it in data["items"]}
    assert by_code["组装"]["status"] == "in_progress" and by_code["组装"]["status_raw"] == "in_progress"
    assert by_code["包装"]["status"] == "planned" and by_code["包装"]["status_raw"] == "pending"
    for field in ("work_order_no", "work_center_code", "predecessor_operation_ids", "route_version"):
        assert by_code["组装"][field] is None

    r = await signed_get(ext_client, OPS_LIST, "production.operations.list", key,
                         {"order_no": "SO-2609-001", "process_type": "包装"})
    assert r.json()["data"]["total"] == 1

    r = await signed_get(ext_client, OPS_LIST, "production.operations.list", key,
                         {"order_no": "SO-2609-001", "plan_date_end": "2026-09-22"})
    assert r.json()["data"]["total"] == 1


async def test_order_links_anchor_required_422(ext_client, external_keys):
    r = await signed_get(ext_client, LINKS_LIST, "production.order_links.list", external_keys["production"])
    assert r.status_code == 422


async def test_order_links_dual_source(ext_client, external_keys, prod_seeded):
    key = external_keys["production"]

    r = await signed_get(ext_client, LINKS_LIST, "production.order_links.list", key, {"order_no": "SO-2609-001"})
    data = r.json()["data"]
    assert data["total"] == 2
    by_type = {it["link_type"]: it for it in data["items"]}
    task = by_type["production_task"]
    assert task["work_order_no"] == "WO-2609-002" and task["order_no"] == "SO-2609-001"
    assert task["line_no"] is None and task["order_line_id"] is None
    assert task["allocated_qty"] == 500.0
    snapshot = by_type["schedule_snapshot"]
    assert snapshot["work_order_no"] is None and snapshot["line_no"] == "1"
    assert snapshot["order_line_id"] == "501" and snapshot["allocated_qty"] is None

    r = await signed_get(ext_client, LINKS_LIST, "production.order_links.list", key,
                         {"work_order_no": "WO-2609-002"})
    data = r.json()["data"]
    assert data["total"] == 1 and data["items"][0]["link_type"] == "production_task"

    r = await signed_get(ext_client, LINKS_LIST, "production.order_links.list", key,
                         {"order_no": "SO-2609-001", "link_type": "schedule_snapshot"})
    data = r.json()["data"]
    assert data["total"] == 1 and data["items"][0]["link_type"] == "schedule_snapshot"


async def test_reports_anchor_required_422(ext_client, external_keys):
    r = await signed_get(ext_client, REPORTS_LIST, "production.reports.list", external_keys["production"])
    assert r.status_code == 422


async def test_reports_list(ext_client, external_keys, prod_seeded):
    key = external_keys["production"]

    r = await signed_get(ext_client, REPORTS_LIST, "production.reports.list", key,
                         {"work_order_no": "WO-2609-002"})
    data = r.json()["data"]
    assert data["total"] == 2
    item = data["items"][0]  # report_date 倒序：09-22 在前
    assert item["report_type"] == "daily_erp" and item["reported_qty"] == 40.0
    assert item["order_no"] == "SO-2609-001" and item["operation_name"] == "组装"
    for field in ("is_reversed", "reversal_of", "revision", "good_qty", "scrap_qty", "uom", "reported_by"):
        assert item[field] is None

    r = await signed_get(ext_client, REPORTS_LIST, "production.reports.list", key,
                         {"work_order_no": "WO-2609-002", "report_date_end": "2026-09-21"})
    assert r.json()["data"]["total"] == 1


async def test_capacity_requires_date_range_422(ext_client, external_keys):
    key = external_keys["production"]
    r = await signed_get(ext_client, CAPACITY_LIST, "production.capacity.list", key)
    assert r.status_code == 422
    r = await signed_get(ext_client, CAPACITY_LIST, "production.capacity.list", key,
                         {"date_start": "2026-09-30", "date_end": "2026-09-23"})
    assert r.status_code == 422


async def test_capacity_aggregation(ext_client, external_keys, prod_seeded):
    key = external_keys["production"]

    r = await signed_get(ext_client, CAPACITY_LIST, "production.capacity.list", key,
                         {"date_start": "2026-09-23", "date_end": "2026-09-23"})
    data = r.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["work_center_code"] == "车间A:assembly"
    assert item["capacity_date"] == "2026-09-23"
    assert item["planned_load_minutes"] == 510.0
    assert item["available_minutes"] == 480.0
    assert item["occupied_slot_count"] == 2
    assert item["shift_id"] is None and item["downtime_minutes"] is None

    r = await signed_get(ext_client, CAPACITY_LIST, "production.capacity.list", key,
                         {"date_start": "2026-09-23", "date_end": "2026-09-27"})
    data = r.json()["data"]
    assert data["total"] == 2
    sunday = next(it for it in data["items"] if it["capacity_date"] == "2026-09-27")
    assert sunday["available_minutes"] == 0.0
    assert sunday["planned_load_minutes"] == 120.0

    r = await signed_get(ext_client, CAPACITY_LIST, "production.capacity.list", key,
                         {"date_start": "2026-09-23", "date_end": "2026-09-27", "schedule_bucket": "lean"})
    assert r.json()["data"]["total"] == 0


async def test_capacity_baseline_freshness(ext_client, external_keys, db):
    """产能为排产快照基线：槽陈旧也返回真实 data_as_of + medium，stale 恒 false（不按 24h 判过期）。"""
    from app.models.production.capacity_slot import CapacitySlot

    db.add(CapacitySlot(department="车间Z", schedule_bucket="lean", slot_date=datetime(2026, 9, 23),
                        hours=2, updated_at=datetime(2026, 8, 27, 16, 10, 46)))
    await db.commit()

    r = await signed_get(ext_client, CAPACITY_LIST, "production.capacity.list",
                         external_keys["production"],
                         {"date_start": "2026-09-23", "date_end": "2026-09-23"})
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["data_as_of"] == "2026-08-27T16:10:46"
    assert data["data_confidence"] == "medium"
    assert data["stale"] is False


async def test_operations_baseline_freshness(ext_client, external_keys, db):
    """工序为计划快照基线：旧 updated_at 返回真实时间 + medium + stale=false。"""
    from app.models.production.process_progress import ProcessProgress

    db.add(ProcessProgress(process_type="组装", order_no="SO-OLD-001", status="pending",
                           plan_date=date(2026, 9, 1), updated_at=datetime(2026, 8, 20, 9, 30)))
    await db.commit()

    r = await signed_get(ext_client, OPS_LIST, "production.operations.list",
                         external_keys["production"], {"order_no": "SO-OLD-001"})
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["data_as_of"] == "2026-08-20T09:30:00"
    assert data["data_confidence"] == "medium"
    assert data["stale"] is False


async def test_reports_baseline_freshness(ext_client, external_keys, db):
    """报工为累计日报基线：旧 updated_at 返回真实时间 + medium + stale=false。"""
    from app.models.production.production_daily_report import ProductionDailyReport

    db.add(ProductionDailyReport(oa_id="DR-OLD", oa_detail_id=9, report_date=date(2026, 8, 20),
                                 production_order_no="WO-OLD-001", completed_qty=10,
                                 updated_at=datetime(2026, 8, 20, 18, 0)))
    await db.commit()

    r = await signed_get(ext_client, REPORTS_LIST, "production.reports.list",
                         external_keys["production"], {"work_order_no": "WO-OLD-001"})
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["data_as_of"] == "2026-08-20T18:00:00"
    assert data["data_confidence"] == "medium"
    assert data["stale"] is False
