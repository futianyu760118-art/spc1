"""调价单 API 回归测试（supplier-last-price 回退取价：无记录 / 空价不得 500）。"""

from decimal import Decimal

from sqlalchemy import text

from app.services.purchase.price_change_service import PriceChangeService
from tests.conftest import login

ADMIN = "admin"
URL = "/api/v1/purchase/price-change/supplier-last-price"


async def test_supplier_last_price_no_record_returns_empty(client):
    """无采购订单记录时返回 200 + data=None（原隐式 return None 触发响应模型校验 500）。"""
    h_admin = await login(client, ADMIN)
    r = await client.get(URL, params={"material_code": "M-NO-PO", "supplier_code": "S-NO-PO"}, headers=h_admin)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"] is None


async def test_supplier_last_price_returns_latest_po_price(client, db):
    """有采购订单时返回该供应商最近一次成交价与日期。"""
    await db.execute(text("""
        INSERT INTO purchase_order (po_no, detail_id, material_code, supplier_code, po_price, po_date, po_status)
        VALUES ('PO-PY-1', 1, 'M-1', 'S-1', 12.3456, '2026-08-01', 'open'),
               ('PO-PY-2', 1, 'M-1', 'S-1', 15.5000, '2026-09-01', 'open')
    """))
    await db.commit()
    h_admin = await login(client, ADMIN)
    r = await client.get(URL, params={"material_code": "M-1", "supplier_code": "S-1"}, headers=h_admin)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["old_price"] == 15.5
    assert body["data"]["old_price_date"] == "2026-09-01"


async def test_supplier_last_price_null_price_returns_empty(client, db):
    """有记录但成交价为空时返回 200 + data=None（不因 float(None) 500）。"""
    await db.execute(text("""
        INSERT INTO purchase_order (po_no, detail_id, material_code, supplier_code, po_price, po_date, po_status)
        VALUES ('PO-PY-NULL', 1, 'M-NULL', 'S-NULL', NULL, '2026-09-01', 'open')
    """))
    await db.commit()
    h_admin = await login(client, ADMIN)
    r = await client.get(URL, params={"material_code": "M-NULL", "supplier_code": "S-NULL"}, headers=h_admin)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"] is None


async def test_create_price_change_pct_over_999_does_not_overflow(db):
    """低价物料涨幅超过 1000% 时应正常落库（NUMERIC(5,2) 会 numeric field overflow 致提交 500）。"""
    await db.execute(text("DELETE FROM purchase_price_change"))
    await db.commit()
    service = PriceChangeService(db)
    record = await service.create_price_change(
        {"supplier_code": "S-PCT-OVERFLOW", "supplier_name": "测试供应商", "title": "大涨幅回归"},
        [{
            "material_code": "M-PCT-OVERFLOW",
            "material_name": "测试物料",
            "old_price": 0.148,
            "new_price": 4.5,
        }],
        submit=False,
        applicant=ADMIN,
    )
    await db.commit()
    assert record is not None
    assert Decimal(str(record["items"][0]["price_change_pct"])) == Decimal("2940.54")
