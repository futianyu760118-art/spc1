"""备份记录列表 API 回归测试（反馈 #120：软删除记录不得出现在备份管理列表）。"""

from sqlalchemy import text

from tests.conftest import login

ADMIN = "admin"
LIST_URL = "/api/v1/system/backups/records"


async def _seed(db) -> dict:
    """种 4 条记录（2 成功 / 1 失败 / 1 已删除），返回 record_name → id 映射。"""
    rows = (await db.execute(text("""
        INSERT INTO backup_record
            (record_name, db_file, uploads_file, db_size, uploads_size,
             source, status, duration_seconds, created_at)
        VALUES
            ('20260901_030000', 'spc_db-20260901_030000.dump', 'uploads-20260901_030000.tar.gz',
             10, 20, 'scheduled', 'success', 30, '2026-09-01 03:00:05'),
            ('20260902_030000', 'spc_db-20260902_030000.dump', 'uploads-20260902_030000.tar.gz',
             10, 20, 'scheduled', 'success', 30, '2026-09-02 03:00:05'),
            ('20260902_120000', 'spc_db-20260902_120000.dump', 'uploads-20260902_120000.tar.gz',
             0, 0, 'manual', 'failed', 5, '2026-09-02 12:00:05'),
            ('20260903_030000', 'spc_db-20260903_030000.dump', 'uploads-20260903_030000.tar.gz',
             0, 0, 'scheduled', 'deleted', 30, '2026-09-03 03:00:05')
        RETURNING id, record_name
    """))).fetchall()
    await db.commit()
    return {name: rid for rid, name in rows}


async def test_list_excludes_deleted_records(client, db):
    """已删除记录不出现在列表，其余状态按时间倒序正常返回；stats 口径不变。"""
    await _seed(db)
    h = await login(client, ADMIN)
    r = await client.get(LIST_URL, headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert [i["record_name"] for i in data["items"]] == [
        "20260902_120000", "20260902_030000", "20260901_030000",
    ]
    assert data["total"] == 3
    assert data["stats"]["success_count"] == 2


async def test_explicit_deleted_status_filter_still_hidden(client, db):
    """显式按 status=deleted 过滤也不返回软删除记录（列表口径统一，不提供已删除视图）。"""
    await _seed(db)
    h = await login(client, ADMIN)
    r = await client.get(LIST_URL, params={"status": "deleted"}, headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


async def test_delete_via_api_then_list_hides(client, db):
    """走删除端点软删除后，该记录从列表消失（反馈 #120 的完整用户路径）。"""
    ids = await _seed(db)
    h = await login(client, ADMIN)
    # 删较旧的成功备份（最新一份成功备份 20260902 受保护不可删）
    r = await client.delete(f"{LIST_URL}/{ids['20260901_030000']}", headers=h)
    assert r.status_code == 200
    assert r.json()["code"] == 0

    r = await client.get(LIST_URL, headers=h)
    data = r.json()["data"]
    names = [i["record_name"] for i in data["items"]]
    assert "20260901_030000" not in names
    assert names == ["20260902_120000", "20260902_030000"]
    assert data["total"] == 2
    assert data["stats"]["success_count"] == 1
