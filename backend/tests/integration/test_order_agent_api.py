"""订单智能体写端点集成测试：白名单/状态守卫/置空/审计溯源/HMAC 授权"""

import time

from sqlalchemy import text

from tests._common_external import build_headers, generate_signature


def _sig_headers(external_keys, query_string=""):
    key = external_keys["order_agent"]
    ts = int(time.time())
    _, sig = generate_signature(ts, key["app_key"], key["app_secret"], "orders.schedule.update", query_string)
    return build_headers(key["app_key"], sig, ts)


async def _seed_order(db, order_no, *, erp_status=None, is_deleted=0):
    await db.execute(text(
        "INSERT INTO sale_order (order_no, line_no, status, erp_status, is_deleted, data_source) "
        "VALUES (:no, '', 'open', :erp, :del, 'manual')"
    ), {"no": order_no, "erp": erp_status, "del": is_deleted})
    await db.commit()


async def test_order_schedule_update_success_and_audit(ext_client, external_keys, db):
    await _seed_order(db, "AGENT-001")
    headers = _sig_headers(external_keys)
    r = await ext_client.put(
        "/api/v1/external/orders/AGENT-001/schedule",
        json={"fields": {"shipping_plan": "2026-11-02", "planned_start_date": "2026-10-21"},
              "request_id": "req-1"},
        headers={**headers, "X-Agent-Run-Id": "run-42"},
    )
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["order_no"] == "AGENT-001"
    assert body["data"]["fields"]["shipping_plan"] == "2026-11-02"
    assert body["data"]["fields"]["planned_start_date"] == "2026-10-21"

    rows = (await db.execute(text(
        "SELECT operator, field_name FROM audit_log WHERE table_name='sale_order' "
        "AND record_id=(SELECT id FROM sale_order WHERE order_no='AGENT-001' LIMIT 1) "
        "ORDER BY id DESC LIMIT 2"
    ))).mappings().all()
    assert any(row["operator"] == "order-agent:run-42" for row in rows)
    assert {row["field_name"] for row in rows} == {"shipping_plan", "planned_start_date"}


async def test_order_schedule_clear_with_null(ext_client, external_keys, db):
    await _seed_order(db, "AGENT-002")
    headers = _sig_headers(external_keys)
    r = await ext_client.put(
        "/api/v1/external/orders/AGENT-002/schedule",
        json={"fields": {"delivery_completed_date": None}},
        headers=headers,
    )
    assert r.json()["code"] == 0
    assert r.json()["data"]["fields"]["delivery_completed_date"] is None


async def test_order_schedule_guards(ext_client, external_keys, db):
    await _seed_order(db, "AGENT-CLOSED", erp_status=3)
    await _seed_order(db, "AGENT-DELETED", is_deleted=1)
    await _seed_order(db, "AGENT-002")
    headers = _sig_headers(external_keys)

    r = await ext_client.put("/api/v1/external/orders/AGENT-MISSING/schedule",
                             json={"fields": {"shipping_plan": "2026-11-02"}}, headers=headers)
    assert r.status_code == 404

    r = await ext_client.put("/api/v1/external/orders/AGENT-CLOSED/schedule",
                             json={"fields": {"shipping_plan": "2026-11-02"}}, headers=headers)
    assert r.status_code == 400

    r = await ext_client.put("/api/v1/external/orders/AGENT-DELETED/schedule",
                             json={"fields": {"shipping_plan": "2026-11-02"}}, headers=headers)
    assert r.status_code == 400

    r = await ext_client.put("/api/v1/external/orders/AGENT-002/schedule",
                             json={"fields": {}}, headers=headers)
    assert r.status_code == 400

    r = await ext_client.put("/api/v1/external/orders/AGENT-002/schedule",
                             json={"fields": {"shipping_plan": "2026-13-99"}}, headers=headers)
    assert r.status_code == 422


async def test_order_schedule_forbidden_without_endpoint_auth(ext_client, external_keys, db):
    await _seed_order(db, "AGENT-003")
    key = external_keys["agent"]
    ts = int(time.time())
    _, sig = generate_signature(ts, key["app_key"], key["app_secret"], "orders.schedule.update", "")
    headers = build_headers(key["app_key"], sig, ts)
    r = await ext_client.put("/api/v1/external/orders/AGENT-003/schedule",
                             json={"fields": {"shipping_plan": "2026-11-02"}}, headers=headers)
    assert r.status_code == 403
