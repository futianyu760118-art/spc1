"""订单对外接口（orders.list）风险概率字段集成测试。

覆盖：risk_probability = risk_score/100 归一化（0-1）；未评估订单返回 null 且不按
risk_level 反推；risk_level 原样返回。
"""

import pytest_asyncio

from tests.integration.test_external_quality_api import signed_get

ORDERS_LIST = "/api/v1/external/orders/list"


@pytest_asyncio.fixture(loop_scope="session")
async def orders_seeded(external_keys, db):
    """1 条已评估订单（risk_score=62.5）+ 1 条有等级但未评估订单。"""
    from app.models.order.sale_order import SaleOrder

    db.add_all([
        SaleOrder(order_no="SO-RP-001", line_no="1", product_code="P-100", order_qty=10,
                  status="open", risk_level="red", risk_score=62.5),
        SaleOrder(order_no="SO-RP-002", line_no="1", product_code="P-200", order_qty=5,
                  status="open", risk_level="yellow"),
    ])
    await db.commit()


async def test_risk_probability_normalized(ext_client, external_keys, orders_seeded):
    r = await signed_get(ext_client, ORDERS_LIST, "orders.list", external_keys["orders"],
                         {"keyword": "SO-RP-001"})
    item = r.json()["data"]["items"][0]
    assert item["risk_level"] == "red"
    assert item["risk_probability"] == 0.625


async def test_order_no_exact_filter(ext_client, external_keys, orders_seeded):
    r = await signed_get(ext_client, ORDERS_LIST, "orders.list", external_keys["orders"],
                         {"order_no": "SO-RP-001"})
    data = r.json()["data"]
    assert data["total"] == 1
    assert [item["order_no"] for item in data["items"]] == ["SO-RP-001"]


async def test_risk_probability_null_when_not_assessed(ext_client, external_keys, orders_seeded):
    r = await signed_get(ext_client, ORDERS_LIST, "orders.list", external_keys["orders"],
                         {"keyword": "SO-RP-002"})
    item = r.json()["data"]["items"][0]
    assert item["risk_level"] == "yellow"
    assert item["risk_probability"] is None


@pytest_asyncio.fixture(loop_scope="session")
async def closed_orders_seeded(external_keys, db):
    """已关闭口径样本：ERP 完成/取消、手工关闭，以及 3 条未关闭（含空交期与 NULL erp_status）。"""
    from datetime import date

    from app.models.order.sale_order import SaleOrder

    db.add_all([
        SaleOrder(order_no="SO-CL-001", line_no="1", customer_code="CLOSED-TEST",
                  status="open", erp_status=3, delivery_completed_date=date(2025, 12, 1),
                  promised_date=date(2026, 1, 1)),
        SaleOrder(order_no="SO-CL-002", line_no="1", customer_code="CLOSED-TEST",
                  status="open", erp_status=3, promised_date=date(2026, 1, 2)),
        SaleOrder(order_no="SO-CL-003", line_no="1", customer_code="CLOSED-TEST",
                  status="closed", is_closed=1, erp_status=1, promised_date=date(2026, 1, 3)),
        SaleOrder(order_no="SO-OPEN-001", line_no="1", customer_code="CLOSED-TEST",
                  status="open", promised_date=date(2026, 3, 1)),
        SaleOrder(order_no="SO-OPEN-002", line_no="1", customer_code="CLOSED-TEST",
                  status="open", erp_status=1, promised_date=date(2026, 2, 1)),
        SaleOrder(order_no="SO-OPEN-003", line_no="1", customer_code="CLOSED-TEST",
                  status="open", erp_status=1),
    ])
    await db.commit()


async def test_default_excludes_closed_and_sorts_promised_date_desc(
    ext_client, external_keys, closed_orders_seeded,
):
    r = await signed_get(ext_client, ORDERS_LIST, "orders.list", external_keys["orders"],
                         {"customer_code": "CLOSED-TEST"})
    data = r.json()["data"]
    numbers = [item["order_no"] for item in data["items"]]
    assert numbers == ["SO-OPEN-001", "SO-OPEN-002", "SO-OPEN-003"], numbers
    assert data["total"] == 3


async def test_explicit_status_can_query_closed(
    ext_client, external_keys, closed_orders_seeded,
):
    r = await signed_get(ext_client, ORDERS_LIST, "orders.list", external_keys["orders"],
                         {"customer_code": "CLOSED-TEST", "status": "completed"})
    numbers = [item["order_no"] for item in r.json()["data"]["items"]]
    assert numbers == ["SO-CL-001"]

    r = await signed_get(ext_client, ORDERS_LIST, "orders.list", external_keys["orders"],
                         {"customer_code": "CLOSED-TEST", "status": "closed"})
    numbers = [item["order_no"] for item in r.json()["data"]["items"]]
    assert numbers == ["SO-CL-003"]
