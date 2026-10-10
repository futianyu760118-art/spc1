"""备份管理核心服务：进程内 job 执行器。

pg_dump / pg_restore / tar 均由 backend 进程 asyncio subprocess 直接执行
（镜像内置 postgresql-client-15，网络直连，与 postgres:15 大版本一致）。
设计文档：docs/备份管理设计-2026-09.md
"""

import asyncio
import hashlib
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.basicdata.backup import BackupConfig, BackupRecord
from app.services.backup.plan import pg_target_from_url, select_outdated_records

logger = logging.getLogger(__name__)

MIN_DUMP_BYTES = 1024 * 1024        # pg_dump 产物 < 1MB 视为失败（沿用 backup-db.sh 守卫）
MIN_FREE_BYTES = 2 * 1024 ** 3      # 空间预检查下限 2GB
SUBPROCESS_TIMEOUT = 4 * 3600      # 单命令超时
MAX_KEPT_JOBS = 20                  # 内存保留的最近 job 数
MAINTENANCE_WHITELIST_PREFIXES = (
    "/api/v1/system/backups",
    "/api/v1/common/ping",
    "/api/v1/basicdata/auth",
)


@dataclass
class JobStep:
    name: str
    status: str = "pending"  # pending / running / ok / fail / skipped


@dataclass
class JobLog:
    ts: str
    level: str  # INF / OK / ERR
    msg: str


@dataclass
class BackupJob:
    job_id: str
    type: str  # backup / restore
    steps: list
    logs: list = field(default_factory=list)
    status: str = "running"  # running / ok / fail
    result: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "type": self.type,
            "status": self.status,
            "steps": [{"name": s.name, "status": s.status} for s in self.steps],
            "logs": [{"ts": l.ts, "level": l.level, "msg": l.msg} for l in self.logs[-200:]],
            "result": self.result,
        }


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _run_cmd(cmd: list, env_extra: dict | None = None) -> tuple[int, str]:
    env = {**os.environ, **(env_extra or {})}
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=SUBPROCESS_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "command timeout"
    return proc.returncode or 0, (out or b"").decode("utf-8", errors="replace")


def _backup_dir() -> Path:
    return Path(get_settings().BACKUP_DIR)


def _uploads_root() -> Path:
    return Path(get_settings().STORAGE_LOCAL_ROOT)


def _storage_is_s3() -> bool:
    return (get_settings().STORAGE_BACKEND or "local").lower() == "s3"


class BackupService:
    """进程内 job 管理器：同一时刻仅允许一个备份/恢复 job（互斥锁）"""

    def __init__(self) -> None:
        self._jobs: dict = {}
        self._job_order: list = []
        self._mutex = asyncio.Lock()
        self._maintenance = False

    # ---------- job 基础 ----------
    def create_job(self, job_type: str, step_names: list) -> BackupJob:
        job = BackupJob(
            job_id=uuid.uuid4().hex[:12],
            type=job_type,
            steps=[JobStep(name) for name in step_names],
        )
        self._jobs[job.job_id] = job
        self._job_order.append(job.job_id)
        while len(self._job_order) > MAX_KEPT_JOBS:
            self._jobs.pop(self._job_order.pop(0), None)
        return job

    def get_job(self, job_id: str) -> Optional[BackupJob]:
        return self._jobs.get(job_id)

    def is_busy(self) -> bool:
        """是否有备份/恢复任务正在执行（供调度器避让，避免误告警）"""
        return self._mutex.locked()

    async def cleanup_stale_running_records(self) -> int:
        """进程重启后，把上次运行遗留的 running 备份记录置为 failed 并清理半成品文件"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(BackupRecord).where(BackupRecord.status == "running")
                )
                stale = result.scalars().all()
                for record in stale:
                    (_backup_dir() / record.db_file).unlink(missing_ok=True)
                    if record.uploads_file:
                        (_backup_dir() / record.uploads_file).unlink(missing_ok=True)
                    record.status = "failed"
                    record.error_message = ((record.error_message or "") + " [服务重启，备份任务中断已自动标记为失败]")[:2000]
                if stale:
                    await db.commit()
                return len(stale)
        except Exception as exc:
            logger.warning("[备份管理] 清理中断备份记录失败: %s", exc)
            return 0

    def _log(self, job: BackupJob, msg: str, level: str = "INF") -> None:
        job.logs.append(JobLog(_now_str(), level, msg))
        logger.info("[备份管理][%s] %s", job.job_id, msg)

    async def _fail(self, job: BackupJob, message: str, record_id: int | None = None,
                    step_index: int | None = None) -> None:
        if step_index is not None:
            job.steps[step_index].status = "fail"
        for step in job.steps:
            if step.status == "running":
                step.status = "fail"
        job.status = "fail"
        self._log(job, message, "ERR")
        if record_id is not None:
            try:
                async with AsyncSessionLocal() as db:
                    record = await db.get(BackupRecord, record_id)
                    if record:
                        record.status = "failed"
                        record.error_message = message[:2000]
                        await db.commit()
            except Exception as exc:
                logger.warning("[备份管理] 失败状态落库异常: %s", exc)

    # ---------- 维护模式 ----------
    def is_maintenance(self) -> bool:
        return self._maintenance

    @staticmethod
    def is_path_allowed(path: str) -> bool:
        if not (path.startswith("/api") or path.startswith("/uploads")):
            return True
        return any(path.startswith(prefix) for prefix in MAINTENANCE_WHITELIST_PREFIXES)

    async def _enter_maintenance(self, job: BackupJob) -> None:
        self._maintenance = True
        _backup_dir().mkdir(parents=True, exist_ok=True)
        (_backup_dir() / ".restoring").write_text(job.job_id, encoding="utf-8")
        await self._pause_background_tasks(job)

    async def _exit_maintenance(self, job: BackupJob) -> None:
        self._maintenance = False
        (_backup_dir() / ".restoring").unlink(missing_ok=True)
        await self._resume_background_tasks(job)

    async def _pause_background_tasks(self, job: BackupJob) -> None:
        # 清单与 app/main.py lifespan 启动清单保持一致
        from app.services.scheduler.backup_scheduler import backup_scheduler
        from app.services.basicdata.sync_scheduler import scheduler
        from app.services.exception.risk_scheduler import risk_scheduler
        from app.services.scheduler.overdue_checker import overdue_checker
        from app.services.scheduler.capacity_sync_scheduler import capacity_sync_scheduler
        from app.services.scheduler.data_supply_alert import data_supply_alert_scheduler
        from app.services.scheduler.approval_timeout_reminder import approval_timeout_reminder
        from app.services.scheduler.mrp_scheduler import mrp_scheduler
        from app.services.basicdata.writeback_worker import writeback_worker

        backup_scheduler.stop()
        scheduler.stop()
        risk_scheduler.stop()
        overdue_checker.stop()
        data_supply_alert_scheduler.stop()
        approval_timeout_reminder.stop()
        capacity_sync_scheduler.stop()
        await mrp_scheduler.stop()
        await writeback_worker.stop()
        self._log(job, "已暂停全部后台任务（定时备份/ERP同步/风险扫描/超期检查/产能同步/数据供给/审批提醒/MRP/回写）")

    async def _resume_background_tasks(self, job: BackupJob) -> None:
        from app.services.scheduler.backup_scheduler import backup_scheduler
        from app.services.basicdata.sync_scheduler import scheduler
        from app.services.exception.risk_scheduler import risk_scheduler
        from app.services.scheduler.overdue_checker import overdue_checker
        from app.services.scheduler.capacity_sync_scheduler import capacity_sync_scheduler
        from app.services.scheduler.data_supply_alert import data_supply_alert_scheduler
        from app.services.scheduler.approval_timeout_reminder import approval_timeout_reminder
        from app.services.scheduler.mrp_scheduler import mrp_scheduler
        from app.services.basicdata.writeback_worker import writeback_worker

        backup_scheduler.start()
        scheduler.start()
        risk_scheduler.start()
        overdue_checker.start()
        data_supply_alert_scheduler.start()
        approval_timeout_reminder.start()
        capacity_sync_scheduler.start()
        mrp_scheduler.start()
        writeback_worker.start()
        self._log(job, "已恢复全部后台任务（含定时备份）")

    # ---------- 备份 ----------
    def run_backup(self, source: str, user_id: int | None = None) -> str:
        job = self.create_job("backup", ["空间预检查", "数据库备份", "附件打包", "完整性校验", "保留策略清理"])
        asyncio.get_running_loop().create_task(self._do_backup(job, source, user_id))
        return job.job_id

    async def _do_backup(self, job: BackupJob, source: str, user_id: int | None) -> None:
        if self._mutex.locked():
            await self._fail(job, "已有备份/恢复任务在执行，请稍后再试", step_index=0)
            return
        async with self._mutex:
            await self._execute_backup(job, source, user_id)

    async def _execute_backup(self, job: BackupJob, source: str, user_id: int | None) -> None:
        """备份执行体（调用方保证已持有互斥锁；恢复流程内的 safety 快照复用此入口）"""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_file = _backup_dir() / f"spc_db-{stamp}.dump"
        # S3 模式下附件存于 MinIO，备份仅含数据库，不生成附件包文件
        uploads_file = None if _storage_is_s3() else _backup_dir() / f"uploads-{stamp}.tar.gz"
        started = time.time()

        record_id: int | None = None
        try:
            async with AsyncSessionLocal() as db:
                record = BackupRecord(record_name=stamp, db_file=db_file.name,
                                      uploads_file=uploads_file.name if uploads_file else "",
                                      source=source, status="running", created_by=user_id)
                db.add(record)
                await db.commit()
                record_id = record.id
            # 步骤0 空间预检查
            job.steps[0].status = "running"
            _backup_dir().mkdir(parents=True, exist_ok=True)
            last_total = await self._last_success_total_bytes()
            free = shutil.disk_usage(_backup_dir()).free
            need = max(last_total * 2, MIN_FREE_BYTES)
            if free < need:
                await self._fail(job, f"磁盘空间不足：剩余 {free >> 20}MB < 需要 {need >> 20}MB", record_id, 0)
                return
            job.steps[0].status = "ok"
            self._log(job, f"空间预检查通过（剩余 {free >> 20}MB）")

            # 步骤1 pg_dump
            job.steps[1].status = "running"
            target = pg_target_from_url(get_settings().DATABASE_URL)
            rc, out = await _run_cmd(
                ["pg_dump", "-h", target["host"], "-p", str(target["port"]), "-U", target["user"],
                 "--format=custom", f"--file={db_file}", target["database"]],
                env_extra={"PGPASSWORD": target["password"]},
            )
            if rc != 0 or not db_file.exists() or db_file.stat().st_size < MIN_DUMP_BYTES:
                db_file.unlink(missing_ok=True)
                if uploads_file:
                    uploads_file.unlink(missing_ok=True)
                await self._fail(job, f"pg_dump 失败: {out.strip()[:800]}", record_id, 1)
                return
            job.steps[1].status = "ok"
            db_size = db_file.stat().st_size
            self._log(job, f"数据库备份完成（{db_size >> 20}MB）")

            # 步骤2 uploads 打包（S3 模式跳过：附件存于 MinIO，备份仅含数据库）
            job.steps[2].status = "running"
            if _storage_is_s3():
                job.steps[2].status = "skipped"
                uploads_size = 0
                self._log(job, "附件存储于 MinIO（S3 模式），本备份不包含附件包")
            else:
                uploads_root = _uploads_root()
                if not uploads_root.exists():
                    db_file.unlink(missing_ok=True)
                    await self._fail(job, f"uploads 目录不存在: {uploads_root}", record_id, 2)
                    return
                rc, out = await _run_cmd(
                    ["tar", "czf", str(uploads_file), "-C", str(uploads_root.parent), uploads_root.name]
                )
                if rc != 0 or not uploads_file.exists():
                    db_file.unlink(missing_ok=True)
                    uploads_file.unlink(missing_ok=True)
                    await self._fail(job, f"uploads 打包失败: {out.strip()[:800]}", record_id, 2)
                    return
                job.steps[2].status = "ok"
                uploads_size = uploads_file.stat().st_size
                self._log(job, f"附件打包完成（{uploads_size >> 20}MB）")

            # 备份文件含全库数据与附件，收紧权限（设计 §6.5）
            os.chmod(db_file, 0o600)
            if uploads_file:
                os.chmod(uploads_file, 0o600)

            # 步骤3 sha256 校验并落库
            job.steps[3].status = "running"
            db_sha = _sha256_file(db_file)
            uploads_sha = _sha256_file(uploads_file) if uploads_file else None
            duration = int(time.time() - started)
            async with AsyncSessionLocal() as db:
                record = await db.get(BackupRecord, record_id)
                record.db_size = db_size
                record.uploads_size = uploads_size
                record.db_sha256 = db_sha
                record.uploads_sha256 = uploads_sha
                record.status = "success"
                record.duration_seconds = duration
                await db.commit()
            job.steps[3].status = "ok"

            # 步骤4 保留清理（safety 快照不触发清理）
            job.steps[4].status = "running"
            removed = 0 if source == "safety" else await self._retention_cleanup()
            job.steps[4].status = "ok"
            if removed:
                self._log(job, f"保留策略清理：删除 {removed} 份旧备份")

            job.status = "ok"
            job.result = {"record_id": record_id, "record_name": stamp}
            self._log(job, f"备份完成，耗时 {duration}s", "OK")
        except Exception as exc:
            await self._fail(job, f"备份异常: {exc}", record_id)

    async def _last_success_total_bytes(self) -> int:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(BackupRecord.db_size, BackupRecord.uploads_size)
                .where(BackupRecord.status == "success")
                .order_by(BackupRecord.created_at.desc()).limit(1)
            )).first()
            return (row[0] + row[1]) if row else 0

    async def _retention_cleanup(self) -> int:
        async with AsyncSessionLocal() as db:
            config = await db.get(BackupConfig, 1)
            retention = config.retention_count if config else 7
            rows = (await db.execute(
                select(BackupRecord).where(BackupRecord.status == "success")
                .order_by(BackupRecord.created_at.desc())
            )).scalars().all()
            stale_ids = select_outdated_records(
                [{"id": r.id} for r in rows], retention
            )
            removed = 0
            for stale_id in stale_ids:
                stale = await db.get(BackupRecord, stale_id)
                if stale:
                    (_backup_dir() / stale.db_file).unlink(missing_ok=True)
                    if stale.uploads_file:
                        (_backup_dir() / stale.uploads_file).unlink(missing_ok=True)
                    stale.status = "deleted"
                    removed += 1
            if removed:
                await db.commit()
            return removed

    # ---------- 恢复 ----------
    def run_restore(self, info: dict, user_id: int | None = None) -> str:
        job = self.create_job("restore", ["恢复前预检", "安全快照", "进入维护模式", "数据库恢复", "附件恢复", "退出维护模式"])
        asyncio.get_running_loop().create_task(self._do_restore(job, info, user_id))
        return job.job_id

    async def _do_restore(self, job: BackupJob, info: dict, user_id: int | None) -> None:
        if self._mutex.locked():
            await self._fail(job, "已有备份/恢复任务在执行，请稍后再试", step_index=0)
            return
        async with self._mutex:
            db_file = _backup_dir() / info["db_file"]
            uploads_file = _backup_dir() / info["uploads_file"]
            try:
                # 0 预检：文件存在 + sha256 匹配，失败则不动任何数据（S3 模式只校验库文件）
                job.steps[0].status = "running"
                if not db_file.exists() or (not _storage_is_s3() and not uploads_file.exists()):
                    await self._fail(job, f"备份文件缺失: {info['db_file']} / {info['uploads_file']}", step_index=0)
                    return
                if (_sha256_file(db_file) != (info.get("db_sha256") or "")
                        or (not _storage_is_s3()
                            and _sha256_file(uploads_file) != (info.get("uploads_sha256") or ""))):
                    await self._fail(job, "备份文件校验失败（sha256 不匹配），文件可能已损坏", step_index=0)
                    return
                job.steps[0].status = "ok"
                self._log(job, "预检通过（文件存在且校验和匹配）")

                # 1 safety 快照（复用备份执行体，不释放互斥锁）
                job.steps[1].status = "running"
                safety_job = self.create_job("backup", ["空间预检查", "数据库备份", "附件打包", "完整性校验", "保留策略清理"])
                self._log(job, f"生成恢复前安全快照（job {safety_job.job_id}）…")
                await self._execute_backup(safety_job, "safety", user_id)
                if safety_job.status != "ok":
                    await self._fail(job, "恢复前安全快照失败，已中止恢复（数据未变动）", step_index=1)
                    return
                safety_name = (safety_job.result or {}).get("record_name")
                job.steps[1].status = "ok"

                # 2 进入维护模式（挡业务流量 + 暂停后台任务）
                job.steps[2].status = "running"
                await self._enter_maintenance(job)
                job.steps[2].status = "ok"

                # 3 数据库恢复：断开其它连接 → pg_restore
                job.steps[3].status = "running"
                target = pg_target_from_url(get_settings().DATABASE_URL)
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                             "WHERE datname = :d AND pid <> pg_backend_pid()"),
                        {"d": target["database"]},
                    )
                    await db.commit()
                self._log(job, "已断开其它数据库连接")
                rc, out = await _run_cmd(
                    ["pg_restore", "-h", target["host"], "-p", str(target["port"]), "-U", target["user"],
                     "--clean", "--if-exists", "--no-owner", f"--dbname={target['database']}", str(db_file)],
                    env_extra={"PGPASSWORD": target["password"]},
                )
                if rc != 0:
                    await self._fail(
                        job,
                        f"pg_restore 失败: {out.strip()[:800]}；可用安全快照 {safety_name} 回退",
                        step_index=3,
                    )
                    await self._best_effort_exit(job)
                    return
                job.steps[3].status = "ok"
                self._log(job, "数据库恢复完成")

                # 4 附件恢复：清空挂载点内容后解包（/app/uploads 是 bind mount 挂载点，不能整目录 mv；
                #    回退能力由步骤 1 的 safety 快照提供）。S3 模式跳过：附件存于 MinIO，不在备份包内
                job.steps[4].status = "running"
                if _storage_is_s3():
                    job.steps[4].status = "skipped"
                    self._log(job, "附件存储于 MinIO（S3 模式），仅恢复数据库")
                else:
                    uploads_root = _uploads_root()
                    if not uploads_root.exists():
                        uploads_root.mkdir(parents=True, exist_ok=True)
                    else:
                        for child in uploads_root.iterdir():
                            if child.is_dir() and not child.is_symlink():
                                shutil.rmtree(child)
                            else:
                                child.unlink(missing_ok=True)
                    self._log(job, "已清空现有附件目录内容")
                    rc, out = await _run_cmd(
                        ["tar", "xzf", str(uploads_file), "-C", str(uploads_root), "--strip-components=1"]
                    )
                    if rc != 0 or not any(uploads_root.iterdir()):
                        await self._fail(job, f"附件恢复失败: {out.strip()[:800]}", step_index=4)
                        await self._best_effort_exit(job)
                        return
                    job.steps[4].status = "ok"
                    self._log(job, "附件恢复完成")

                # 5 退出维护模式
                job.steps[5].status = "running"
                await self._exit_maintenance(job)
                job.steps[5].status = "ok"

                job.status = "ok"
                job.result = {"record_id": info["id"], "record_name": info["record_name"],
                              "safety_record_name": safety_name}
                self._log(job, "恢复完成（热恢复），建议刷新页面重新加载数据", "OK")
            except Exception as exc:
                await self._fail(job, f"恢复异常: {exc}")
                await self._best_effort_exit(job)

    async def _best_effort_exit(self, job: BackupJob) -> None:
        try:
            if self._maintenance:
                await self._exit_maintenance(job)
        except Exception as exc:
            self._log(job, f"退出维护模式失败，需人工检查（删除 BACKUP_DIR/.restoring 并重启 backend）: {exc}", "ERR")

    # ---------- 删除 ----------
    async def delete_backup_files(self, db_file: str, uploads_file: str) -> None:
        (_backup_dir() / db_file).unlink(missing_ok=True)
        if uploads_file:
            (_backup_dir() / uploads_file).unlink(missing_ok=True)


backup_service = BackupService()
