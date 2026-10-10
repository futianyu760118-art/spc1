"""系统管理 — 备份管理 API（backend 自执行，无外部 agent）"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.basicdata.backup import BackupConfig, BackupRecord
from app.schemas.backup import BackupConfigUpdate, RestoreRequest
from app.schemas.common import ResponseModel
from app.services.backup.backup_service import backup_service
from app.services.backup.plan import compute_next_run, confirm_matches

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_id(user: dict) -> Optional[int]:
    try:
        return int((user or {}).get("id") or (user or {}).get("sub") or 0) or None
    except (TypeError, ValueError):
        return None


async def _audit(db: AsyncSession, user: dict, action: str, target: str) -> None:
    try:
        await log_audit(
            db, "backup_record", 0, action, field_name=target,
            operator=(user or {}).get("username") or "system",
        )
        await db.commit()
    except Exception as exc:
        logger.warning("[备份管理] 审计落库失败: %s", exc)


@router.get("/records", response_model=ResponseModel[dict])
async def list_records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(PermissionChecker("backup", "read")),
    db: AsyncSession = Depends(get_db),
):
    # 软删除记录（手动删除/保留策略清理）不再出现在备份管理列表
    query = select(BackupRecord).where(BackupRecord.status != "deleted")
    if source:
        query = query.where(BackupRecord.source == source)
    if status:
        query = query.where(BackupRecord.status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (await db.execute(
        query.order_by(BackupRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    items = [{
        "id": r.id, "record_name": r.record_name,
        "db_file": r.db_file, "uploads_file": r.uploads_file,
        "db_size": r.db_size, "uploads_size": r.uploads_size,
        "db_sha256": r.db_sha256, "uploads_sha256": r.uploads_sha256,
        "source": r.source, "status": r.status,
        "duration_seconds": r.duration_seconds, "error_message": r.error_message,
        "created_by": r.created_by,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
    } for r in rows]

    success_stats = (await db.execute(
        select(func.count(BackupRecord.id), func.coalesce(func.sum(BackupRecord.db_size + BackupRecord.uploads_size), 0),
               func.max(BackupRecord.created_at))
        .where(BackupRecord.status == "success")
    )).first()
    config = await db.get(BackupConfig, 1)
    next_run = None
    if config and config.enabled:
        next_run = compute_next_run(frequency=config.frequency, schedule_time=config.schedule_time,
                                    weekday=config.weekday, now=datetime.now())
    backup_dir = Path(get_settings().BACKUP_DIR)
    free_bytes = shutil.disk_usage(backup_dir).free if backup_dir.exists() else None
    return ResponseModel(data={
        "items": items, "total": total, "page": page, "page_size": page_size,
        "stats": {
            "success_count": success_stats[0] or 0,
            "total_size": success_stats[1] or 0,
            "latest_success_at": success_stats[2].strftime("%Y-%m-%d %H:%M:%S") if success_stats[2] else None,
            "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else None,
            "disk_free_bytes": free_bytes,
            "backup_dir": str(backup_dir),
            "storage_backend": (get_settings().STORAGE_BACKEND or "local"),
        },
    })


@router.post("/run", response_model=ResponseModel[dict])
async def run_backup(
    current_user: dict = Depends(PermissionChecker("backup", "manage")),
    db: AsyncSession = Depends(get_db),
):
    job_id = backup_service.run_backup(source="manual", user_id=_user_id(current_user))
    await _audit(db, current_user, "backup_run", job_id)
    return ResponseModel(message="备份任务已启动", data={"job_id": job_id})


@router.post("/records/{record_id}/restore", response_model=ResponseModel[dict])
async def restore_record(
    record_id: int,
    body: RestoreRequest,
    current_user: dict = Depends(PermissionChecker("backup", "manage")),
    db: AsyncSession = Depends(get_db),
):
    if not confirm_matches(body.confirm_text):
        raise HTTPException(status_code=400, detail="确认文字不正确，请输入「确认恢复」")
    record = await db.get(BackupRecord, record_id)
    if not record or record.status != "success":
        raise HTTPException(status_code=404, detail="备份记录不存在或不可恢复")
    info = {
        "id": record.id, "record_name": record.record_name,
        "db_file": record.db_file, "uploads_file": record.uploads_file,
        "db_sha256": record.db_sha256, "uploads_sha256": record.uploads_sha256,
    }
    job_id = backup_service.run_restore(info, user_id=_user_id(current_user))
    await _audit(db, current_user, "backup_restore", record.record_name)
    return ResponseModel(message="恢复任务已启动", data={"job_id": job_id})


@router.delete("/records/{record_id}", response_model=ResponseModel)
async def delete_record(
    record_id: int,
    current_user: dict = Depends(PermissionChecker("backup", "manage")),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(BackupRecord, record_id)
    if not record or record.status != "success":
        raise HTTPException(status_code=404, detail="备份记录不存在或不可删除")
    latest_id = (await db.execute(
        select(BackupRecord.id).where(BackupRecord.status == "success")
        .order_by(BackupRecord.created_at.desc()).limit(1)
    )).scalar()
    if latest_id == record_id:
        raise HTTPException(status_code=400, detail="最新一份成功备份不可删除")
    await backup_service.delete_backup_files(record.db_file, record.uploads_file)
    record.status = "deleted"
    await _audit(db, current_user, "backup_delete", record.record_name)
    return ResponseModel(message="已删除")


@router.get("/records/{record_id}/download")
async def download_record(
    record_id: int,
    type: str = Query(pattern="^(db|uploads)$"),
    current_user: dict = Depends(PermissionChecker("backup", "manage")),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(BackupRecord, record_id)
    if not record or record.status not in ("success", "deleted"):
        raise HTTPException(status_code=404, detail="备份记录不存在")
    file_name = record.db_file if type == "db" else record.uploads_file
    path = Path(get_settings().BACKUP_DIR) / file_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    await _audit(db, current_user, "backup_download", file_name)

    def iter_file():
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/config", response_model=ResponseModel[dict])
async def get_config(
    current_user: dict = Depends(PermissionChecker("backup", "read")),
    db: AsyncSession = Depends(get_db),
):
    config = await db.get(BackupConfig, 1)
    if not config:
        config = BackupConfig(id=1)
        db.add(config)
        await db.commit()
    return ResponseModel(data={
        "enabled": config.enabled, "frequency": config.frequency,
        "schedule_time": config.schedule_time, "weekday": config.weekday,
        "retention_count": config.retention_count,
    })


@router.put("/config", response_model=ResponseModel[dict])
async def update_config(
    body: BackupConfigUpdate,
    current_user: dict = Depends(PermissionChecker("backup", "manage")),
    db: AsyncSession = Depends(get_db),
):
    config = await db.get(BackupConfig, 1)
    if not config:
        config = BackupConfig(id=1)
        db.add(config)
    config.enabled = body.enabled
    config.frequency = body.frequency
    config.schedule_time = body.schedule_time
    config.weekday = body.weekday
    config.retention_count = body.retention_count
    config.updated_by = _user_id(current_user)
    await _audit(db, current_user, "backup_config", f"{body.frequency}@{body.schedule_time}")
    return ResponseModel(data={
        "enabled": config.enabled, "frequency": config.frequency,
        "schedule_time": config.schedule_time, "weekday": config.weekday,
        "retention_count": config.retention_count,
    })


@router.get("/jobs/{job_id}", response_model=ResponseModel[dict])
async def get_job(
    job_id: str,
    current_user: dict = Depends(PermissionChecker("backup", "read")),
):
    job = backup_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return ResponseModel(data=job.to_dict())
