import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.common import ResponseModel
from app.schemas.writeback import WritebackConfigUpsert
from app.core.database import get_erp_write_engine

router = APIRouter()


@router.get("/config", response_model=ResponseModel[list])
async def list_config(current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        text("SELECT * FROM writeback_sql_config ORDER BY writeback_type")
    )).mappings().all()
    items = [dict(r) for r in rows]
    for it in items:
        for k in ("target_key_fields", "field_mapping_json"):
            if isinstance(it.get(k), str):
                try:
                    it[k] = json.loads(it[k])
                except Exception:
                    pass
    return ResponseModel(data=items)


@router.post("/config", response_model=ResponseModel[dict])
async def upsert_config(req: WritebackConfigUpsert, current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(
        text("SELECT id FROM writeback_sql_config WHERE writeback_type = :t"),
        {"t": req.writeback_type},
    )).first()
    payload = req.model_dump()
    payload["target_key_fields_json"] = json.dumps(payload.pop("target_key_fields"))
    if payload.get("field_mapping_json") is not None:
        payload["field_mapping_json"] = json.dumps(payload["field_mapping_json"])
    if existing:
        await db.execute(
            text("""
                UPDATE writeback_sql_config SET
                  description=:description, target_table=:target_table,
                  target_key_fields=CAST(:target_key_fields_json AS jsonb),
                  update_sql_template=:update_sql_template,
                  field_mapping_json=CAST(:field_mapping_json AS jsonb),
                  enqueue_trigger=:enqueue_trigger,
                  max_retries=:max_retries, enabled=:enabled,
                  updated_at=now()
                WHERE writeback_type=:writeback_type
            """),
            {**payload, "field_mapping_json": payload.get("field_mapping_json")},
        )
    else:
        await db.execute(
            text("""
                INSERT INTO writeback_sql_config
                  (writeback_type, description, target_table, target_key_fields,
                   update_sql_template, field_mapping_json, enqueue_trigger,
                   max_retries, enabled, created_by)
                VALUES
                  (:writeback_type, :description, :target_table,
                   CAST(:target_key_fields_json AS jsonb), :update_sql_template,
                   CAST(:field_mapping_json AS jsonb), :enqueue_trigger,
                   :max_retries, :enabled, :created_by)
            """),
            {**payload, "field_mapping_json": payload.get("field_mapping_json"),
             "created_by": current_user.get("username")},
        )
    await db.commit()
    return ResponseModel(data={"writeback_type": req.writeback_type, "upserted": True})


@router.post("/config/{writeback_type}/test", response_model=ResponseModel[dict])
async def test_config(writeback_type: str, current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(
        text("SELECT update_sql_template, target_table FROM writeback_sql_config "
             "WHERE writeback_type = :t"),
        {"t": writeback_type},
    )).mappings().first()
    if not cfg:
        raise HTTPException(status_code=404, detail="config not found")
    sample = (await db.execute(
        text("SELECT target_keys, payload FROM writeback_queue "
             "WHERE writeback_type = :t ORDER BY id DESC LIMIT 1"),
        {"t": writeback_type},
    )).mappings().first()
    if not sample:
        raise HTTPException(status_code=400, detail="队列里没有样本可用于测试")
    target_keys = sample["target_keys"] if isinstance(sample["target_keys"], dict) else json.loads(sample["target_keys"])
    payload = sample["payload"] if isinstance(sample["payload"], dict) else json.loads(sample["payload"])
    from app.services.basicdata.writeback_helpers import render_sql
    sql, params = render_sql(cfg["update_sql_template"], target_keys, payload)
    engine = get_erp_write_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="ERP_DB_URL_WRITE 未配置")
    with engine.begin() as conn:
        from sqlalchemy import text as sql_text
        result = conn.execute(sql_text(sql), params)
        conn.execute(sql_text("ROLLBACK"))
        rows = result.rowcount
    return ResponseModel(data={"sql": sql, "params_keys": list(params.keys()), "rows_matched": rows})
