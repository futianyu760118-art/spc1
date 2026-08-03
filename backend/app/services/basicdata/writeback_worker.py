"""回写队列 Worker — 每 N 秒扫描 pending 队列,执行 ERP UPDATE"""
import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, get_erp_write_engine
from app.services.basicdata.writeback_helpers import render_sql
from app.models.basicdata.writeback_sql_config import WritebackSqlConfig

logger = logging.getLogger(__name__)
settings = get_settings()

BACKOFF_MINUTES = [1, 5, 30, 120, 480, 1440]


class WritebackWorker:
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.last_poll_at: Optional[datetime] = None

    async def _claim_batch(self, db: AsyncSession, batch_size: int) -> list[dict]:
        """用 FOR UPDATE SKIP LOCKED 抢占一批 pending|failed 记录"""
        rows = (await db.execute(
            text("""
                SELECT q.id, q.writeback_type, q.target_keys, q.payload,
                       q.retry_count, q.enqueued_at, q.business_pk
                FROM writeback_queue q
                JOIN writeback_sql_config c ON c.writeback_type = q.writeback_type
                WHERE q.status IN ('pending','failed')
                  AND c.enabled = true
                  AND (q.next_retry_at IS NULL OR q.next_retry_at <= now())
                ORDER BY q.enqueued_at ASC
                LIMIT :bs
                FOR UPDATE OF q SKIP LOCKED
            """),
            {"bs": batch_size},
        )).mappings().all()
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        await db.execute(
            text("UPDATE writeback_queue SET status='processing', picked_at=now() "
                 "WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        await db.commit()
        return [dict(r) for r in rows]

    async def _process_one(self, q: dict) -> None:
        """单条处理:渲染 SQL → 执行 → 写 log → 标记 done/failed"""
        task_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        async with AsyncSessionLocal() as db:
            try:
                cfg = (await db.execute(
                    text("SELECT update_sql_template, max_retries, target_table "
                         "FROM writeback_sql_config WHERE writeback_type = :wt"),
                    {"wt": q["writeback_type"]},
                )).mappings().first()
                if not cfg:
                    raise RuntimeError(f"config not found for {q['writeback_type']}")
                target_keys = q["target_keys"] if isinstance(q["target_keys"], dict) else json.loads(q["target_keys"])
                payload = q["payload"] if isinstance(q["payload"], dict) else json.loads(q["payload"])
                sql_template, params = render_sql(cfg["update_sql_template"], target_keys, payload)
                engine = get_erp_write_engine()
                if engine is None:
                    raise RuntimeError("ERP_DB_URL_WRITE 未配置")
                with engine.begin() as conn:
                    from sqlalchemy import text as sql_text
                    result = conn.execute(sql_text(sql_template), params)
                    rows_affected = result.rowcount
                finished_at = datetime.utcnow()
                duration_ms = int((finished_at - started_at).total_seconds() * 1000)
                async with AsyncSessionLocal() as log_db:
                    await log_db.execute(
                        text("""
                            INSERT INTO writeback_log
                              (task_id, queue_id, writeback_type, status,
                               sql_executed, rows_affected, duration_ms, started_at, finished_at)
                            VALUES (:tid, :qid, :wt, 'success', :sql, :ra, :dm, :sa, :fa)
                        """),
                        {"tid": task_id, "qid": q["id"], "wt": q["writeback_type"],
                         "sql": sql_template, "ra": rows_affected, "dm": duration_ms,
                         "sa": started_at, "fa": finished_at},
                    )
                    await log_db.execute(
                        text("UPDATE writeback_queue SET status='done', finished_at=now(), "
                             "last_error=NULL WHERE id = :id"),
                        {"id": q["id"]},
                    )
                    await log_db.execute(
                        text("UPDATE purchase_order SET last_writeback_at = :fa, "
                             "last_writeback_status = 'success' WHERE id = :id"),
                        {"fa": finished_at, "id": int(q["business_pk"])},
                    )
                    await log_db.commit()
                logger.info(f"writeback done: queue_id={q['id']} type={q['writeback_type']} "
                            f"rows_affected={rows_affected} duration_ms={duration_ms}")
            except Exception as e:
                await self._handle_failure(q, e, task_id, started_at)

    async def _handle_failure(self, q: dict, exc: Exception, task_id: str, started_at: datetime) -> None:
        err = f"{type(exc).__name__}: {exc}"
        async with AsyncSessionLocal() as db:
            cfg_row = (await db.execute(
                text("SELECT max_retries FROM writeback_sql_config WHERE writeback_type = :wt"),
                {"wt": q["writeback_type"]},
            )).first()
            max_retries = cfg_row[0] if cfg_row else 6
            new_retry = q["retry_count"] + 1
            if new_retry >= max_retries:
                new_status, next_retry = "dead", None
            else:
                new_status = "failed"
                delay_min = BACKOFF_MINUTES[min(new_retry - 1, len(BACKOFF_MINUTES) - 1)]
                next_retry = datetime.utcnow() + timedelta(minutes=delay_min)
            await db.execute(
                text("""
                    UPDATE writeback_queue
                    SET status = :st, retry_count = :rc, next_retry_at = :nr,
                        last_error = :le, finished_at = CASE WHEN :st='dead' THEN now() ELSE finished_at END
                    WHERE id = :id
                """),
                {"st": new_status, "rc": new_retry, "nr": next_retry, "le": err, "id": q["id"]},
            )
            await db.execute(
                text("""
                    INSERT INTO writeback_log
                      (task_id, queue_id, writeback_type, status, error_detail, started_at, finished_at)
                    VALUES (:tid, :qid, :wt, 'failed', :ed, :sa, now())
                """),
                {"tid": task_id, "qid": q["id"], "wt": q["writeback_type"],
                 "ed": traceback.format_exc(), "sa": started_at},
            )
            if new_status == "dead":
                await db.execute(
                    text("UPDATE purchase_order SET last_writeback_status = 'failed' "
                         "WHERE id = :id"),
                    {"id": int(q["business_pk"])},
                )
            await db.commit()
        logger.error(f"writeback failed: queue_id={q['id']} type={q['writeback_type']} retry={new_retry} err={err}")

    async def _reap_stuck(self, db: AsyncSession, timeout_seconds: int) -> int:
        """把超时未完成的 processing 记录重新放回队列"""
        res = await db.execute(
            text("""
                UPDATE writeback_queue SET status='failed',
                    next_retry_at = now() + interval '1 minute',
                    last_error = 'claim timeout, requeued by reaper'
                WHERE status='processing' AND picked_at < now() - (:t || ' seconds')::interval
            """),
            {"t": str(timeout_seconds)},
        )
        await db.commit()
        return res.rowcount or 0

    async def _loop(self):
        while self.running:
            try:
                if not settings.writeback_enabled:
                    logger.info("[writeback] disabled, sleeping")
                    await asyncio.sleep(60)
                    continue
                if not settings.erp_db_url_write:
                    logger.warning("[writeback] ERP_DB_URL_WRITE 未配置,worker 跳过执行")
                    await asyncio.sleep(60)
                    continue
                self.last_poll_at = datetime.utcnow()
                async with AsyncSessionLocal() as db:
                    claimed = await self._claim_batch(db, settings.writeback_batch_size)
                for q in claimed:
                    await self._process_one(q)
                async with AsyncSessionLocal() as db:
                    reaped = await self._reap_stuck(db, settings.writeback_claim_timeout)
                    if reaped:
                        logger.info(f"[writeback] reaper requeued {reaped} stuck rows")
            except asyncio.CancelledError:
                logger.info("[writeback] cancelled, exiting")
                break
            except Exception as e:
                logger.error(f"[writeback] loop error: {e}", exc_info=True)
            await asyncio.sleep(settings.writeback_poll_interval)

    def start(self):
        if not settings.writeback_enabled or not settings.erp_db_url_write:
            logger.info("[writeback] 未启动(WRITEBACK_ENABLED 或 ERP_DB_URL_WRITE 未配置)")
            return
        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info("[writeback] worker 已启动")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("[writeback] worker 已停止")


writeback_worker = WritebackWorker()
