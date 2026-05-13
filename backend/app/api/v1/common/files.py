"""通用文件上传/下载/管理 API

所有业务模块附件统一走此入口，对接 Storage 抽象层 + FileAsset 登记表。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import PermissionChecker
from app.core.storage import get_storage
from app.models.masterdata.file_asset import FileAsset
from app.schemas.common import ResponseModel
from app.schemas.masterdata.file_asset import FileAssetOut, FileStatsOut
from app.services.common.file_service import FileService

router = APIRouter()
settings = get_settings()


# ---------- 上传 ----------
@router.post("/upload", response_model=ResponseModel[FileAssetOut])
async def upload_file(
    file: UploadFile = File(...),
    namespace: str = Query("misc", description="业务命名空间"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """任意登录用户均可上传。受 mime 白名单 + 大小限制约束。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(content) > settings.STORAGE_MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件超过 {settings.STORAGE_MAX_FILE_SIZE // 1024 // 1024}MB 限制",
        )

    mime = file.content_type or "application/octet-stream"
    if settings.STORAGE_ALLOWED_MIMES and mime not in settings.STORAGE_ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {mime}")

    storage = get_storage()
    stored = storage.save(content, file.filename or "unnamed", mime, namespace)

    svc = FileService(db)
    asset = await svc.register(
        key=stored.key,
        url=stored.url,
        name=stored.name,
        mime=stored.mime,
        size=stored.size,
        namespace=namespace,
        uploader_id=current_user.get("user_id"),
        uploader_name=current_user.get("username"),
    )
    await db.commit()
    await db.refresh(asset)
    return ResponseModel(data=FileAssetOut.model_validate(asset))


# ---------- 列表（admin only） ----------
@router.get("", response_model=ResponseModel[dict])
async def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    namespace: Optional[str] = None,
    mime: Optional[str] = None,
    uploader: Optional[str] = None,
    keyword: Optional[str] = None,
    is_orphan: Optional[bool] = None,
    current_user: dict = Depends(PermissionChecker("masterdata.files", "read")),
    db: AsyncSession = Depends(get_db),
):
    conds = [FileAsset.deleted_at.is_(None)]
    if namespace:
        conds.append(FileAsset.namespace == namespace)
    if mime:
        conds.append(FileAsset.mime.ilike(f"%{mime}%"))
    if uploader:
        conds.append(FileAsset.uploader_name.ilike(f"%{uploader}%"))
    if keyword:
        like = f"%{keyword}%"
        conds.append(or_(
            FileAsset.name.ilike(like),
            FileAsset.uploader_name.ilike(like),
        ))
    if is_orphan is not None:
        conds.append(FileAsset.is_orphan.is_(is_orphan))

    base = select(FileAsset).where(and_(*conds))
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0

    rows = (await db.execute(
        base.order_by(FileAsset.uploaded_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return ResponseModel(data={
        "items": [FileAssetOut.model_validate(r).model_dump() for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    })


# ---------- 统计 ----------
@router.get("/stats", response_model=ResponseModel[FileStatsOut])
async def file_stats(
    current_user: dict = Depends(PermissionChecker("masterdata.files", "read")),
    db: AsyncSession = Depends(get_db),
):
    svc = FileService(db)
    data = await svc.stats()
    return ResponseModel(data=FileStatsOut(**data))


# ---------- 单删 ----------
@router.delete("/{asset_id}", response_model=ResponseModel[dict])
async def delete_file(
    asset_id: int,
    current_user: dict = Depends(PermissionChecker("masterdata.files", "delete")),
    db: AsyncSession = Depends(get_db),
):
    svc = FileService(db)
    ok = await svc.hard_delete(asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文件不存在")
    await db.commit()
    return ResponseModel(data={"deleted": asset_id})


# ---------- 清理孤儿 ----------
@router.post("/cleanup-orphans", response_model=ResponseModel[dict])
async def cleanup_orphans(
    days: int = Query(7, ge=0, le=365),
    current_user: dict = Depends(PermissionChecker("masterdata.files", "delete")),
    db: AsyncSession = Depends(get_db),
):
    svc = FileService(db)
    cleaned = await svc.cleanup_orphans(days)
    await db.commit()
    return ResponseModel(data={"cleaned": cleaned, "days": days})


# ---------- 流式下载（鉴权） ----------
@router.get("/download/{key:path}")
async def download_file(
    key: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    storage = get_storage()
    # 校验文件存在性
    asset = (await db.execute(
        select(FileAsset).where(FileAsset.key == key, FileAsset.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        fh = storage.open(key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件已被清理")

    def _iter():
        try:
            while True:
                chunk = fh.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            fh.close()

    headers = {"Content-Disposition": f'attachment; filename="{asset.name}"'}
    return StreamingResponse(_iter(), media_type=asset.mime or "application/octet-stream", headers=headers)
