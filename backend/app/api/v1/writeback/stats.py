from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.common import ResponseModel
from app.services.basicdata.writeback_worker import writeback_worker

router = APIRouter()


@router.get("/stats", response_model=ResponseModel[dict])
async def stats(current_user: dict = Depends(get_current_user),
                db: AsyncSession = Depends(get_db)):
    depth = (await db.execute(
        text("SELECT status, count(*) FROM writeback_queue GROUP BY status")
    )).mappings().all()
    queue_depth = {r["status"]: r["count"] for r in depth}
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    success_rate_row = (await db.execute(
        text("SELECT "
             "  count(*) FILTER (WHERE status='success') AS ok, "
             "  count(*) AS total "
             "FROM writeback_log WHERE created_at >= :t"),
        {"t": one_hour_ago},
    )).mappings().first()
    ok = success_rate_row["ok"] or 0
    total = success_rate_row["total"] or 0
    avg_row = (await db.execute(
        text("SELECT COALESCE(AVG(duration_ms),0) FROM writeback_log "
             "WHERE created_at >= :t AND status='success'"),
        {"t": one_hour_ago},
    )).scalar()
    failures = (await db.execute(
        text("SELECT id AS queue_id, writeback_type, last_error AS error, "
             "COALESCE(finished_at, picked_at, created_at) AS at "
             "FROM writeback_queue WHERE status='dead' "
             "ORDER BY id DESC LIMIT 10")
    )).mappings().all()
    by_type = (await db.execute(
        text("SELECT writeback_type, "
             "  sum(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending, "
             "  sum(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed, "
             "  sum(CASE WHEN status='dead' THEN 1 ELSE 0 END) AS dead "
             "FROM writeback_queue GROUP BY writeback_type")
    )).mappings().all()
    done_24h = (await db.execute(
        text("SELECT count(*) FROM writeback_queue "
             "WHERE status='done' AND finished_at >= :t"),
        {"t": datetime.utcnow() - timedelta(hours=24)},
    )).scalar()
    queue_depth["done_24h"] = done_24h
    return ResponseModel(data={
        "queue_depth": queue_depth,
        "success_rate_1h": (ok / total) if total else None,
        "avg_duration_ms_1h": int(avg_row or 0),
        "by_type": [dict(r) for r in by_type],
        "recent_failures": [dict(r) for r in failures],
        "worker": {
            "running": writeback_worker.running,
            "last_poll_at": writeback_worker.last_poll_at.isoformat() if writeback_worker.last_poll_at else None,
        },
    })
