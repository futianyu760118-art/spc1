from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.common import ResponseModel, PageResult
from app.schemas.writeback import RetryQueueRequest, AbandonQueueRequest

router = APIRouter()


@router.get("/queue", response_model=ResponseModel[PageResult])
async def list_queue(
    status: str | None = Query(None),
    writeback_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    where = ["1=1"]
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    if status:
        where.append("status = :status")
        params["status"] = status
    if writeback_type:
        where.append("writeback_type = :wt")
        params["writeback_type"] = writeback_type
    rows = (await db.execute(
        text(f"SELECT * FROM writeback_queue WHERE {' AND '.join(where)} "
             f"ORDER BY id DESC LIMIT :limit OFFSET :offset"),
        params,
    )).mappings().all()
    total = (await db.execute(
        text(f"SELECT count(*) FROM writeback_queue WHERE {' AND '.join(where)}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )).scalar()
    items = [dict(r) for r in rows]
    for it in items:
        for k in ("target_keys", "payload"):
            if isinstance(it.get(k), str):
                try:
                    import json
                    it[k] = json.loads(it[k])
                except Exception:
                    pass
    return ResponseModel(data=PageResult(items=items, total=total, page=page, page_size=page_size))


@router.get("/queue/{queue_id}", response_model=ResponseModel[dict])
async def get_queue_detail(queue_id: int, current_user: dict = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("SELECT * FROM writeback_queue WHERE id = :id"), {"id": queue_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="queue row not found")
    item = dict(row)
    for k in ("target_keys", "payload"):
        if isinstance(item.get(k), str):
            import json
            item[k] = json.loads(item[k])
    return ResponseModel(data=item)


@router.post("/queue/{queue_id}/retry", response_model=ResponseModel[dict])
async def retry_queue(queue_id: int, current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        text("UPDATE writeback_queue SET status='pending', retry_count=0, "
             "next_retry_at=now(), last_error=NULL "
             "WHERE id=:id AND status IN ('failed','dead')"),
        {"id": queue_id},
    )
    await db.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=409, detail="queue 行不存在或状态非 failed/dead")
    return ResponseModel(data={"queue_id": queue_id, "retried": True})


@router.post("/queue/{queue_id}/abandon", response_model=ResponseModel[dict])
async def abandon_queue(queue_id: int, current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        text("UPDATE writeback_queue SET status='abandoned', finished_at=now() "
             "WHERE id=:id AND status NOT IN ('done','abandoned')"),
        {"id": queue_id},
    )
    await db.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=409, detail="queue 行不存在或已 done")
    return ResponseModel(data={"queue_id": queue_id, "abandoned": True})
