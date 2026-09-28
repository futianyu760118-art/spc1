"""对外接口数据时效契约集成回归测试（orders / order-details / boms / materials / suppliers）。

覆盖：data_as_of = 源表全表 max 与最近成功同步时间的较晚者、过滤器命中为空仍返回真实时效、
源表空且从未同步 → code=503 结构化错误（含调用日志）、request_id 回显。
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from tests.integration.test_external_quality_api import signed_get

ORDERS_LIST = "/api/v1/external/orders/list"
ORDER_DETAILS_LIST = "/api/v1/external/order-details/list"
BOMS_TREE = "/api/v1/external/boms/tree"
MATERIALS_LIST = "/api/v1/external/materials/list"
SUPPLIERS_LIST = "/api/v1/external/suppliers/list"

_SYNC_TYPES = ("orders", "order_details", "boms", "bom_details", "materials_masterdata", "suppliers")

FRESHNESS_ENDPOINTS = [
    (ORDERS_LIST, "orders.list", {}, "orders", "订单"),
    (ORDER_DETAILS_LIST, "order_details.list", {}, "order_details", "订单明细"),
    (BOMS_TREE, "boms.tree", {"bom_id": "101"}, "boms", "BOM"),
    (MATERIALS_LIST, "materials.list", {}, "materials_masterdata", "物料"),
    (SUPPLIERS_LIST, "suppliers.list", {}, "suppliers", "供应商"),
]


def _stamp(hours_ago: int) -> datetime:
    return (datetime.now() - timedelta(hours=hours_ago)).replace(microsecond=0)


async def _clear_sync_configs(db) -> None:
    from app.models.basicdata.sync_sql_config import SyncSqlConfig

    await db.execute(delete(SyncSqlConfig).where(SyncSqlConfig.sync_type.in_(_SYNC_TYPES)))
    await db.commit()


async def _seed_source_rows(db, endpoint_code: str, ts) -> None:
    """按端点构造最小源数据（时间戳 ts）；order_details 需要订单头满足外键。"""
    from app.models.basicdata.bom import Bom
    from app.models.basicdata.bom_detail import BomDetail
    from app.models.basicdata.material import Material
    from app.models.basicdata.supplier import Supplier
    from app.models.order.sale_order import SaleOrder, SaleOrderLine

    if endpoint_code == "orders.list":
        db.add(SaleOrder(order_no="SO-FR-010", line_no="1", customer="客户B",
                         customer_code="C-002", product_code="P-100", order_qty=10,
                         status="open", updated_at=ts))
    elif endpoint_code == "order_details.list":
        order = SaleOrder(order_no="SO-FR-011", line_no="1", product_code="P-100",
                          order_qty=10, status="open", updated_at=ts)
        db.add(order)
        await db.flush()
        db.add(SaleOrderLine(sale_order_id=order.id, order_no="SO-FR-011", line_no="1",
                             product_code="P-100", order_qty=10, status="open", updated_at=ts))
    elif endpoint_code == "boms.tree":
        db.add(Bom(bom_id="101", bom_no="BOM-001", bom_version="V1", bom_type="production",
                   update_time=ts))
        db.add(BomDetail(bom_id="101", line_no="1", material_id=1001, standard_qty=1,
                         update_time=ts))
    elif endpoint_code == "materials.list":
        db.add(Material(erp_material_id=1001, material_code="M-100", material_name="物料A",
                        material_type="外购", unit_of_measure="个", is_purchase=1,
                        is_produce=0, status=1, is_deleted=0, update_time=ts))
    elif endpoint_code == "suppliers.list":
        db.add(Supplier(supplier_code="S-001", supplier_name="供应商A", status=1,
                        update_time=ts))
    else:
        raise AssertionError(f"未知端点: {endpoint_code}")
    await db.commit()


async def _add_sync_config(db, sync_type: str, ts) -> None:
    from app.models.basicdata.sync_sql_config import SyncSqlConfig

    db.add(SyncSqlConfig(sync_type=sync_type, description="pytest", sql_text="SELECT 1",
                         sync_interval="1h", sync_strategy="full", sync_priority=5,
                         sync_enabled=True, is_active=True, last_sync_time=ts))
    await db.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def freshness_seeded(external_keys, db):
    """5 个接口各自的最小源数据，时间戳统一为 1 小时前（high 置信度）。"""
    from app.models.basicdata.bom import Bom
    from app.models.basicdata.bom_detail import BomDetail
    from app.models.basicdata.material import Material
    from app.models.basicdata.supplier import Supplier
    from app.models.order.sale_order import SaleOrder, SaleOrderLine

    await _clear_sync_configs(db)
    ts = _stamp(1)
    order = SaleOrder(order_no="SO-FR-001", line_no="1", customer="客户A", customer_code="C-001",
                      product_code="P-100", order_qty=10, status="open", updated_at=ts)
    db.add(order)
    await db.flush()
    db.add_all([
        SaleOrderLine(sale_order_id=order.id, order_no="SO-FR-001", line_no="1",
                      product_code="P-100", order_qty=10, status="open", updated_at=ts),
        Bom(bom_id="101", bom_no="BOM-001", bom_version="V1", bom_type="production", update_time=ts),
        BomDetail(bom_id="101", line_no="1", material_id=1001, standard_qty=2, update_time=ts),
        Material(erp_material_id=1001, material_code="M-100", material_name="物料A",
                 material_type="外购", unit_of_measure="个", is_purchase=1, is_produce=0,
                 status=1, is_deleted=0, update_time=ts),
        Supplier(supplier_code="S-001", supplier_name="供应商A", status=1, update_time=ts),
    ])
    await db.commit()
    return {"data_as_of": ts.isoformat()}


@pytest.mark.parametrize("path,endpoint_code,extra,sync_type,label", FRESHNESS_ENDPOINTS)
async def test_freshness_fields_and_request_id(
    ext_client, external_keys, freshness_seeded, path, endpoint_code, extra, sync_type, label,
):
    params = {**extra, "request_id": "fr-001"}
    r = await signed_get(ext_client, path, endpoint_code, external_keys["orders"], params)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["data_as_of"] == freshness_seeded["data_as_of"]
    assert data["data_confidence"] == "high"
    assert data["stale"] is False
    assert data["request_id"] == "fr-001"


@pytest.mark.parametrize("path,endpoint_code,extra,sync_type,label", FRESHNESS_ENDPOINTS)
async def test_source_unavailable_returns_503(
    ext_client, external_keys, db, path, endpoint_code, extra, sync_type, label,
):
    """源表无数据且相关同步从未成功 → code=503 信封错误，并按失败记调用日志。"""
    from app.models.basicdata.data_supply import DataSupplyCallLog

    await _clear_sync_configs(db)
    r = await signed_get(ext_client, path, endpoint_code, external_keys["orders"], extra)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 503
    assert body["data"] is None
    assert f"「{label}」数据源不可用" in body["message"]

    log = (await db.execute(
        select(DataSupplyCallLog).order_by(DataSupplyCallLog.id.desc()).limit(1)
    )).scalar_one()
    assert log.response_status == 503
    assert log.data_type == endpoint_code
    assert log.error_message and f"「{label}」数据源不可用" in log.error_message


async def test_empty_filter_keeps_source_freshness(ext_client, external_keys, freshness_seeded):
    r = await signed_get(ext_client, ORDERS_LIST, "orders.list", external_keys["orders"],
                         {"customer_code": "NO-SUCH-CUSTOMER"})
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["items"] == [] and data["total"] == 0
    assert data["data_as_of"] == freshness_seeded["data_as_of"]
    assert data["data_confidence"] == "high"
    assert data["stale"] is False


@pytest.mark.parametrize("path,endpoint_code,extra,sync_type,label", FRESHNESS_ENDPOINTS)
async def test_sync_time_wins_over_older_table(
    ext_client, external_keys, db, path, endpoint_code, extra, sync_type, label,
):
    """同步成功即视为数据已刷新：同步时间晚于源表最后修改时，data_as_of 取同步时间。"""
    await _clear_sync_configs(db)
    table_ts = _stamp(5)
    sync_ts = _stamp(2)
    await _seed_source_rows(db, endpoint_code, table_ts)
    await _add_sync_config(db, sync_type, sync_ts)
    try:
        r = await signed_get(ext_client, path, endpoint_code, external_keys["orders"], extra)
        data = r.json()["data"]
        assert data["data_as_of"] == sync_ts.isoformat()
        assert data["data_confidence"] == "high"
    finally:
        await _clear_sync_configs(db)


@pytest.mark.parametrize("path,endpoint_code,extra,sync_type,label", FRESHNESS_ENDPOINTS)
async def test_table_time_wins_over_older_sync(
    ext_client, external_keys, db, path, endpoint_code, extra, sync_type, label,
):
    """源表最后修改晚于同步成功时间（如手工维护）时，data_as_of 取源表时间。"""
    await _clear_sync_configs(db)
    table_ts = _stamp(1)
    sync_ts = _stamp(5)
    await _seed_source_rows(db, endpoint_code, table_ts)
    await _add_sync_config(db, sync_type, sync_ts)
    try:
        r = await signed_get(ext_client, path, endpoint_code, external_keys["orders"], extra)
        data = r.json()["data"]
        assert data["data_as_of"] == table_ts.isoformat()
        assert data["data_confidence"] == "high"
    finally:
        await _clear_sync_configs(db)


async def test_boms_tree_uses_latest_of_bom_and_detail(ext_client, external_keys, db):
    """BOM 源表为多列 max：bom 与 bom_detail 取较晚者。"""
    from app.models.basicdata.bom import Bom
    from app.models.basicdata.bom_detail import BomDetail

    await _clear_sync_configs(db)
    bom_ts = _stamp(5)
    detail_ts = _stamp(1)
    db.add(Bom(bom_id="103", bom_no="BOM-003", bom_version="V1", bom_type="production",
               update_time=bom_ts))
    db.add(BomDetail(bom_id="103", line_no="1", material_id=1003, standard_qty=1,
                     update_time=detail_ts))
    await db.commit()
    r = await signed_get(ext_client, BOMS_TREE, "boms.tree", external_keys["orders"],
                         {"bom_id": "103"})
    data = r.json()["data"]
    assert data["data_as_of"] == detail_ts.isoformat()


async def test_boms_multi_sync_uses_oldest_source(ext_client, external_keys, db):
    """多同步类型共担同一数据集：同步时间取 min（薄弱环节），再与源表 max 取较晚者。"""
    await _clear_sync_configs(db)
    table_ts = _stamp(7)
    boms_ts = _stamp(1)
    bom_details_ts = _stamp(5)
    await _seed_source_rows(db, "boms.tree", table_ts)
    await _add_sync_config(db, "boms", boms_ts)
    await _add_sync_config(db, "bom_details", bom_details_ts)
    try:
        r = await signed_get(ext_client, BOMS_TREE, "boms.tree", external_keys["orders"],
                             {"bom_id": "101"})
        data = r.json()["data"]
        assert data["data_as_of"] == bom_details_ts.isoformat()
        assert data["data_confidence"] == "high"
    finally:
        await _clear_sync_configs(db)


async def test_confidence_low_and_stale_after_validity(ext_client, external_keys, db):
    """非基线数据超过 24h 有效时限：low + stale=true，不因源表有数据就判新鲜。"""
    await _clear_sync_configs(db)
    ts = _stamp(30)
    await _seed_source_rows(db, "orders.list", ts)
    r = await signed_get(ext_client, ORDERS_LIST, "orders.list", external_keys["orders"])
    data = r.json()["data"]
    assert data["data_as_of"] == ts.isoformat()
    assert data["data_confidence"] == "low"
    assert data["stale"] is True
