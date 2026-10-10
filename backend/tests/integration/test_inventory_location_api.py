"""库存库位手动维护 API 测试（PUT /basicdata/inventory/{id}/location + GET /inventory 合成输出）。"""

from sqlalchemy import text

from tests.conftest import login

ADMIN = "admin"
URL = "/api/v1/basicdata/inventory/{inv_id}/location"


async def _seed_inventory(db) -> int:
    inv_id = (await db.execute(text("""
        INSERT INTO scm_inventory
            (material_id, material_code, material_name, wh_id, wh_code, wh_name,
             location_id, location_name, qty_on_hand, locked_qty, balance_qty,
             qty_in_transit, unit_price, ending_balance, batch_no, data_source)
        VALUES (1001, 'M-1001', '测试物料', 2001, 'W-2001', '测试仓库',
                3001, 'ERP库位A', 10, 0, 10, 0, 1.5, 15, 'B001', 'erp')
        RETURNING id
    """))).scalar_one()
    await db.commit()
    return inv_id


async def _seed_location(db, location_id: int, name: str, source: str = "erp"):
    await db.execute(text("""
        INSERT INTO scm_location
            (location_id, location_code, location_name, location_full_name, is_deleted, data_source)
        VALUES (:lid, :name, :name, :name, 0, :src)
    """), {"lid": location_id, "name": name, "src": source})
    await db.commit()


async def test_select_existing_location(client, db):
    inv_id = await _seed_inventory(db)
    await _seed_location(db, 5001, "优选库位")
    h = await login(client, ADMIN)
    r = await client.put(URL.format(inv_id=inv_id), json={"location_id": 5001}, headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["location_id"] == 5001
    assert data["location_name"] == "优选库位"
    assert data["erp_location_name"] == "ERP库位A"
    assert data["is_location_manual"] is True

    row = (await db.execute(text(
        "SELECT manual_location_id, manual_location_name FROM scm_inventory WHERE id = :i"
    ), {"i": inv_id})).one()
    assert row.manual_location_id == 5001
    assert row.manual_location_name == "优选库位"


async def test_create_new_location_by_name(client, db):
    inv_id = await _seed_inventory(db)
    h = await login(client, ADMIN)
    r = await client.put(URL.format(inv_id=inv_id), json={"location_name": "手工货架X"}, headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["location_name"] == "手工货架X"
    assert data["is_location_manual"] is True

    loc = (await db.execute(text(
        "SELECT location_id, data_source, depth, parent_id, detail_flag FROM scm_location WHERE location_name = '手工货架X'"
    ))).one()
    assert loc.location_id < 0
    assert loc.data_source == "manual"
    assert loc.depth == 0
    assert loc.parent_id is None
    assert loc.detail_flag == 1

    r2 = await client.put(URL.format(inv_id=inv_id), json={"location_name": "手工货架X"}, headers=h)
    assert r2.status_code == 200
    cnt = (await db.execute(text("SELECT count(*) FROM scm_location WHERE location_name = '手工货架X'"))).scalar_one()
    assert cnt == 1


async def test_restore_erp_location(client, db):
    inv_id = await _seed_inventory(db)
    h = await login(client, ADMIN)
    await client.put(URL.format(inv_id=inv_id), json={"location_name": "手工货架Y"}, headers=h)
    r = await client.put(URL.format(inv_id=inv_id), json={"location_name": None}, headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["location_name"] == "ERP库位A"
    assert data["erp_location_name"] == "ERP库位A"
    assert data["is_location_manual"] is False

    row = (await db.execute(text(
        "SELECT manual_location_id, manual_location_name FROM scm_inventory WHERE id = :i"
    ), {"i": inv_id})).one()
    assert row.manual_location_id is None
    assert row.manual_location_name is None


async def test_get_inventory_coalesced_output(client, db):
    inv_id = await _seed_inventory(db)
    h = await login(client, ADMIN)
    await client.put(URL.format(inv_id=inv_id), json={"location_name": "展示库位"}, headers=h)
    r = await client.get("/api/v1/basicdata/inventory", params={"page": 1, "page_size": 20}, headers=h)
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    it = items[0]
    assert it["location_name"] == "展示库位"
    assert it["erp_location_name"] == "ERP库位A"
    assert it["is_location_manual"] is True


async def test_update_missing_inventory_404(client):
    h = await login(client, ADMIN)
    r = await client.put(URL.format(inv_id=99999), json={"location_name": "x"}, headers=h)
    assert r.status_code == 404


async def test_update_missing_location_404(client, db):
    inv_id = await _seed_inventory(db)
    h = await login(client, ADMIN)
    r = await client.put(URL.format(inv_id=inv_id), json={"location_id": 88888}, headers=h)
    assert r.status_code == 404


async def test_update_empty_name_400(client, db):
    inv_id = await _seed_inventory(db)
    h = await login(client, ADMIN)
    r = await client.put(URL.format(inv_id=inv_id), json={"location_name": ""}, headers=h)
    assert r.status_code == 400
