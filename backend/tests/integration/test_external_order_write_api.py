"""订单受控写接口：备注/状态、幂等、状态机与 HMAC 授权。"""

import time

from sqlalchemy import text

from tests._common_external import build_headers, generate_signature


def _sig_headers(external_keys, endpoint_code="orders.write"):
    key = external_keys["order_agent"]
    ts = int(time.time())
    _, sig = generate_signature(ts, key["app_key"], key["app_secret"], endpoint_code, "")
    return build_headers(key["app_key"], sig, ts)


async def _seed_order(
    db,
    order_no,
    *,
    erp_status=None,
    is_closed=0,
    is_deleted=0,
    status="open",
    remark=None,
):
    await db.execute(
        text(
            "INSERT INTO sale_order "
            "(order_no, line_no, status, erp_status, is_closed, is_deleted, remark, data_source) "
            "VALUES (:no, '', :status, :erp, :closed, :deleted, :remark, 'manual')"
        ),
        {
            "no": order_no,
            "status": status,
            "erp": erp_status,
            "closed": is_closed,
            "deleted": is_deleted,
            "remark": remark,
        },
    )
    await db.commit()


async def _get_order(db, order_no):
    return (
        await db.execute(
            text(
                "SELECT status, is_closed, remark FROM sale_order "
                "WHERE order_no = :no ORDER BY id DESC LIMIT 1"
            ),
            {"no": order_no},
        )
    ).mappings().one()


async def test_update_note_success_and_idempotent_replay(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-001", erp_status=1, remark="old")
    headers = {**_sig_headers(external_keys), "X-Agent-Run-Id": "run-1"}
    payload = {
        "operation": "order.update_note",
        "changes": {"remark": "new note"},
        "idempotencyKey": "idem-note-1",
        "request_id": "req-note-1",
    }

    first = await ext_client.put(
        "/api/v1/external/orders/WRITE-001/write", json=payload, headers=headers
    )
    body = first.json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["ok"] is True
    assert data["operation"] == "order.update_note"
    assert data["target"] == {"orderNo": "WRITE-001"}
    assert data["before"] == {"remark": "old"}
    assert data["after"] == {"remark": "new note"}
    assert data["appliedAt"].endswith("+08:00")
    assert data["idempotent_replay"] is False
    assert (await _get_order(db, "WRITE-001"))["remark"] == "new note"

    audit_count = (
        await db.execute(
            text(
                "SELECT count(1) FROM audit_log WHERE table_name='sale_order' "
                "AND record_id=(SELECT id FROM sale_order WHERE order_no='WRITE-001' LIMIT 1)"
            )
        )
    ).scalar_one()

    second = await ext_client.put(
        "/api/v1/external/orders/WRITE-001/write", json=payload, headers=headers
    )
    replay = second.json()
    assert replay["code"] == 0, replay
    replay_data = replay["data"]
    assert replay_data["idempotent_replay"] is True
    assert replay_data["before"] == data["before"]
    assert replay_data["after"] == data["after"]
    assert replay_data["appliedAt"] == data["appliedAt"]
    assert (await _get_order(db, "WRITE-001"))["remark"] == "new note"
    replay_audit_count = (
        await db.execute(
            text(
                "SELECT count(1) FROM audit_log WHERE table_name='sale_order' "
                "AND record_id=(SELECT id FROM sale_order WHERE order_no='WRITE-001' LIMIT 1)"
            )
        )
    ).scalar_one()
    assert replay_audit_count == audit_count


async def test_idempotency_conflict(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-002", erp_status=1, remark="old")
    headers = _sig_headers(external_keys)
    first = await ext_client.put(
        "/api/v1/external/orders/WRITE-002/write",
        json={
            "operation": "order.update_note",
            "changes": {"remark": "first"},
            "idempotencyKey": "idem-conflict",
        },
        headers=headers,
    )
    assert first.json()["code"] == 0

    second = await ext_client.put(
        "/api/v1/external/orders/WRITE-002/write",
        json={
            "operation": "order.update_note",
            "changes": {"remark": "second"},
            "idempotencyKey": "idem-conflict",
        },
        headers=headers,
    )
    body = second.json()
    assert body["code"] == 409
    assert body["message"].startswith("IDEMPOTENCY_CONFLICT")
    assert (await _get_order(db, "WRITE-002"))["remark"] == "first"


async def test_update_status_close_and_reopen(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-003", erp_status=1)
    headers = _sig_headers(external_keys)

    closed = await ext_client.put(
        "/api/v1/external/orders/WRITE-003/write",
        json={
            "operation": "order.update_status",
            "changes": {"status": "closed"},
            "idempotencyKey": "idem-status-1",
        },
        headers=headers,
    )
    body = closed.json()
    assert body["code"] == 0, body
    assert body["data"]["before"] == {"status": "open", "is_closed": 0}
    assert body["data"]["after"] == {"status": "closed", "is_closed": 1}
    row = await _get_order(db, "WRITE-003")
    assert row["status"] == "closed" and row["is_closed"] == 1

    reopened = await ext_client.put(
        "/api/v1/external/orders/WRITE-003/write",
        json={
            "operation": "order.update_status",
            "changes": {"status": "open"},
            "idempotencyKey": "idem-status-2",
        },
        headers=headers,
    )
    body = reopened.json()
    assert body["code"] == 0, body
    assert body["data"]["after"] == {"status": "open", "is_closed": 0}
    row = await _get_order(db, "WRITE-003")
    assert row["status"] == "open" and row["is_closed"] == 0


async def test_status_blocked_for_erp_closed(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-004", erp_status=3, is_closed=1, status="closed")
    headers = _sig_headers(external_keys)
    r = await ext_client.put(
        "/api/v1/external/orders/WRITE-004/write",
        json={
            "operation": "order.update_status",
            "changes": {"status": "open"},
            "idempotencyKey": "idem-status-3",
        },
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 400
    assert "ERP 关闭" in body["message"]
    row = await _get_order(db, "WRITE-004")
    assert row["status"] == "closed" and row["is_closed"] == 1


async def test_note_allowed_on_closed_order(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-005", erp_status=3, is_closed=1, status="closed", remark="old")
    headers = _sig_headers(external_keys)
    r = await ext_client.put(
        "/api/v1/external/orders/WRITE-005/write",
        json={
            "operation": "order.update_note",
            "changes": {"remark": "closed note"},
            "idempotencyKey": "idem-note-2",
        },
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0, body
    assert (await _get_order(db, "WRITE-005"))["remark"] == "closed note"


async def test_note_clear_and_max_length(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-006", erp_status=1, remark="old")
    headers = _sig_headers(external_keys)
    r = await ext_client.put(
        "/api/v1/external/orders/WRITE-006/write",
        json={
            "operation": "order.update_note",
            "changes": {"remark": ""},
            "idempotencyKey": "idem-note-clear",
        },
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0, body
    assert body["data"]["after"] == {"remark": ""}
    assert (await _get_order(db, "WRITE-006"))["remark"] is None

    too_long = await ext_client.put(
        "/api/v1/external/orders/WRITE-006/write",
        json={
            "operation": "order.update_note",
            "changes": {"remark": "x" * 2001},
            "idempotencyKey": "idem-note-long",
        },
        headers=headers,
    )
    assert too_long.json()["code"] == 400


async def test_order_not_found(ext_client, external_keys):
    r = await ext_client.put(
        "/api/v1/external/orders/WRITE-MISSING/write",
        json={
            "operation": "order.update_note",
            "changes": {"remark": "x"},
            "idempotencyKey": "idem-missing",
        },
        headers=_sig_headers(external_keys),
    )
    body = r.json()
    assert body["code"] == 404
    assert "订单不存在" in body["message"]


async def test_unsupported_operation_and_invalid_status(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-007", erp_status=1)
    headers = _sig_headers(external_keys)
    unsupported = await ext_client.put(
        "/api/v1/external/orders/WRITE-007/write",
        json={
            "operation": "order.delete",
            "changes": {},
            "idempotencyKey": "idem-unsupported",
        },
        headers=headers,
    )
    body = unsupported.json()
    assert body["code"] == 400
    assert body["message"].startswith("CAPABILITY_UNSUPPORTED")

    invalid_status = await ext_client.put(
        "/api/v1/external/orders/WRITE-007/write",
        json={
            "operation": "order.update_status",
            "changes": {"status": "completed"},
            "idempotencyKey": "idem-invalid-status",
        },
        headers=headers,
    )
    assert invalid_status.json()["code"] == 400


async def test_deleted_order_blocked(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-008", erp_status=1, is_deleted=1)
    r = await ext_client.put(
        "/api/v1/external/orders/WRITE-008/write",
        json={
            "operation": "order.update_note",
            "changes": {"remark": "x"},
            "idempotencyKey": "idem-deleted",
        },
        headers=_sig_headers(external_keys),
    )
    body = r.json()
    assert body["code"] == 400
    assert "已删除" in body["message"]


async def test_requires_orders_write_permission(ext_client, external_keys, db):
    await _seed_order(db, "WRITE-009", erp_status=1)
    key = external_keys["orders"]
    ts = int(time.time())
    _, sig = generate_signature(ts, key["app_key"], key["app_secret"], "orders.write", "")
    headers = build_headers(key["app_key"], sig, ts)
    r = await ext_client.put(
        "/api/v1/external/orders/WRITE-009/write",
        json={
            "operation": "order.update_note",
            "changes": {"remark": "x"},
            "idempotencyKey": "idem-forbidden",
        },
        headers=headers,
    )
    assert r.status_code == 403
