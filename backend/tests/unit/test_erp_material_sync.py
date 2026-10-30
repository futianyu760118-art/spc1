"""物料同步：ERP 修改物料编码时按 erp_material_id 兜底匹配。"""

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.basicdata.material import Material
from app.services.basicdata.erp_sync_service import ERPSyncService


async def test_sync_materials_matches_erp_id_when_code_changed(db):
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(Material).where(
                (Material.erp_material_id == 57336)
                | (Material.material_code.in_(["7.S.145", "7.S.FD-001"]))
            )
        )
        session.add(
            Material(
                erp_material_id=57336,
                material_code="7.S.145",
                material_name="雅马哈飞达（16MM）",
                material_type="辅件",
                unit_of_measure="pcs",
                is_purchase=0,
                is_produce=0,
                status=1,
                erp_sync_flag=0,
                is_deleted=0,
                data_source="erp",
            )
        )
        await session.commit()

    service = ERPSyncService(db)

    async def fake_connect():
        return None

    async def fake_load_sql_config(sync_type):
        return "SELECT 1", {
            "id": "erp_material_id",
            "物料编码": "material_code",
            "物料名称": "material_name",
        }

    async def fake_execute_erp_sql(sql_text, params):
        return [
            {
                "id": 57336,
                "物料编码": "7.S.FD-001",
                "物料名称": "飞达（16MM）",
            }
        ]

    service._connect_erp = fake_connect
    service._load_sql_config = fake_load_sql_config
    service._execute_erp_sql = fake_execute_erp_sql
    service._close_erp = lambda keep_alive=False: None

    result = await service.sync_materials_masterdata()

    assert result["errors"] == []
    assert result["created"] == 0
    assert result["updated"] == 1

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Material).where(Material.erp_material_id == 57336)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].material_code == "7.S.FD-001"
