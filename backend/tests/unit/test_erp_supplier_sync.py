"""供应商同步：ERP 修改供应商编码时按 erp_supply_id 兜底匹配。"""

from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.basicdata.supplier import Supplier
from app.models.basicdata.sync_sql_config import SyncSqlConfig
from app.services.basicdata.erp_sync_service import ERPSyncService
from app.services.basicdata.sync_scheduler import SyncScheduler


async def test_sync_suppliers_matches_erp_id_when_code_changed(db):
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(Supplier).where(
                (Supplier.erp_supply_id == 93292)
                | (Supplier.supplier_code.in_(["HJGY.948", "HJGY.948c"]))
            )
        )
        session.add(
            Supplier(
                supplier_code="HJGY.948c",
                supplier_name="深圳市恒创微电子有限公司",
                erp_supply_id=93292,
                data_source="erp",
            )
        )
        await session.commit()

    service = ERPSyncService(db)

    async def fake_connect():
        return None

    async def fake_load_sql_config(sync_type):
        return "SELECT 1", {
            "id": "erp_supply_id",
            "供应商编码": "supplier_code",
            "供应商名称": "supplier_name",
        }

    async def fake_execute_erp_sql(sql_text, params):
        return [
            {
                "id": 93292,
                "供应商编码": "HJGY.948",
                "供应商名称": "深圳市恒创微电子有限公司",
            }
        ]

    service._connect_erp = fake_connect
    service._load_sql_config = fake_load_sql_config
    service._execute_erp_sql = fake_execute_erp_sql
    service._close_erp = lambda keep_alive=False: None

    result = await service.sync_suppliers()

    assert result["errors"] == []
    assert result["created"] == 0
    assert result["updated"] == 1

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Supplier).where(Supplier.erp_supply_id == 93292)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].supplier_code == "HJGY.948"


async def test_scheduler_failure_keeps_cursor_and_delays_retry(db):
    old_time = datetime.now() - timedelta(days=1)
    await db.execute(
        delete(SyncSqlConfig).where(SyncSqlConfig.sync_type == "pytest_supplier_sync")
    )
    config = SyncSqlConfig(
        sync_type="pytest_supplier_sync",
        sql_text="SELECT 1",
        sync_interval="1d",
        sync_strategy="incremental",
        last_sync_time=old_time,
        next_sync_time=old_time,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    await SyncScheduler()._update_sync_status(db, config, "failed", "boom")
    await db.commit()
    await db.refresh(config)

    assert config.last_sync_status == "failed"
    assert config.last_sync_time == old_time
    assert config.next_sync_time > datetime.now()
