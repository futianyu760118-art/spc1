"""回写服务:enqueue / dedupe / Worker 消费辅助"""
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.writeback_queue import WritebackQueue

logger = logging.getLogger(__name__)


async def enqueue_writeback(
    db: AsyncSession,
    *,
    writeback_type: str,
    business_table: str,
    business_pk: str,
    target_keys: dict,
    payload: dict,
    enqueued_by: str,
    enqueued_by_user: Optional[str] = None,
) -> dict:
    """入队一条回写任务;同 (writeback_type, business_pk) 在 pending|processing 状态去重。

    返回 {"queue_id": int, "deduplicated": bool}
    """
    tk_json = json.dumps(target_keys, ensure_ascii=False, default=str)
    pl_json = json.dumps(payload, ensure_ascii=False, default=str)

    existing = (await db.execute(
        text("SELECT id FROM writeback_queue "
             "WHERE writeback_type = :wt AND business_pk = :pk "
             "AND status IN ('pending','processing') "
             "ORDER BY id DESC LIMIT 1"),
        {"wt": writeback_type, "pk": business_pk},
    )).first()
    if existing:
        await db.execute(
            text("UPDATE writeback_queue SET "
                 "target_keys = CAST(:tk AS jsonb), "
                 "payload = CAST(:pl AS jsonb), "
                 "enqueued_at = now(), enqueued_by = :eb, enqueued_by_user = :ebu "
                 "WHERE id = :id"),
            {"tk": tk_json, "pl": pl_json, "eb": enqueued_by,
             "ebu": enqueued_by_user, "id": existing[0]},
        )
        await db.flush()
        return {"queue_id": existing[0], "deduplicated": True}
    new_row = WritebackQueue(
        writeback_type=writeback_type,
        business_table=business_table,
        business_pk=business_pk,
        target_keys=tk_json,
        payload=pl_json,
        status="pending",
        retry_count=0,
        enqueued_by=enqueued_by,
        enqueued_by_user=enqueued_by_user,
    )
    db.add(new_row)
    await db.flush()
    return {"queue_id": new_row.id, "deduplicated": False}
