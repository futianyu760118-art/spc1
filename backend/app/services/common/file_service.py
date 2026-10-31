"""文件资产服务

封装 attach/detach/cleanup_orphans 逻辑，业务层通过此服务把 storage 对接到 DB。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.models.basicdata.file_asset import FileAsset


class FileService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage()

    async def register(
        self,
        *,
        key: str,
        url: str,
        name: str,
        mime: Optional[str],
        size: int,
        namespace: str,
        uploader_id: Optional[int],
        uploader_name: Optional[str],
    ) -> FileAsset:
        """登记一条文件记录（is_orphan=True，等待业务 attach）"""
        asset = FileAsset(
            key=key,
            url=url,
            name=name,
            mime=mime,
            size=size,
            namespace=namespace,
            uploader_id=uploader_id,
            uploader_name=uploader_name,
            ref_count=0,
            is_orphan=True,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def attach(self, keys: Iterable[str], namespace: str, biz_ref: Optional[str] = None) -> int:
        """业务引用：ref_count+1，is_orphan=False，绑定 biz_ref"""
        keys = [k for k in (keys or []) if k]
        if not keys:
            return 0
        stmt = (
            update(FileAsset)
            .where(FileAsset.key.in_(keys))
            .values(
                ref_count=FileAsset.ref_count + 1,
                is_orphan=False,
                namespace=namespace,
                biz_ref=biz_ref,
            )
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def detach(self, keys: Iterable[str]) -> int:
        """业务解引用：ref_count-1；归零则软删 + 物理清理"""
        keys = [k for k in (keys or []) if k]
        if not keys:
            return 0
        rows = (await self.db.execute(
            select(FileAsset).where(FileAsset.key.in_(keys))
        )).scalars().all()
        affected = 0
        for asset in rows:
            asset.ref_count = max(0, (asset.ref_count or 0) - 1)
            if asset.ref_count == 0:
                asset.is_orphan = True
                asset.deleted_at = datetime.now()
                try:
                    self.storage.delete(asset.key)
                except Exception:
                    pass
            affected += 1
        await self.db.flush()
        return affected

    async def hard_delete(self, asset_id: int) -> bool:
        asset = (await self.db.execute(
            select(FileAsset).where(FileAsset.id == asset_id)
        )).scalar_one_or_none()
        if not asset:
            return False
        try:
            self.storage.delete(asset.key)
        except Exception:
            pass
        asset.deleted_at = datetime.now()
        asset.is_orphan = True
        await self.db.flush()
        return True

    async def cleanup_orphans(self, days: int = 7) -> int:
        """清理 N 天前的孤儿文件（未引用且未软删除）"""
        cutoff = datetime.now() - timedelta(days=max(0, days))
        rows = (await self.db.execute(
            select(FileAsset).where(
                FileAsset.is_orphan == True,  # noqa: E712
                FileAsset.deleted_at.is_(None),
                FileAsset.uploaded_at <= cutoff,
            )
        )).scalars().all()
        cleaned = 0
        for asset in rows:
            try:
                self.storage.delete(asset.key)
            except Exception:
                pass
            asset.deleted_at = datetime.now()
            cleaned += 1
        await self.db.flush()
        return cleaned

    async def stats(self) -> dict:
        seven_days_ago = datetime.now() - timedelta(days=7)
        total_count = (await self.db.execute(
            select(func.count()).select_from(FileAsset).where(FileAsset.deleted_at.is_(None))
        )).scalar() or 0
        total_size = (await self.db.execute(
            select(func.coalesce(func.sum(FileAsset.size), 0)).where(FileAsset.deleted_at.is_(None))
        )).scalar() or 0
        orphan_count = (await self.db.execute(
            select(func.count()).select_from(FileAsset)
            .where(FileAsset.is_orphan == True, FileAsset.deleted_at.is_(None))  # noqa: E712
        )).scalar() or 0
        uploaded_last_7d = (await self.db.execute(
            select(func.count()).select_from(FileAsset)
            .where(FileAsset.uploaded_at >= seven_days_ago, FileAsset.deleted_at.is_(None))
        )).scalar() or 0
        return {
            "total_count": int(total_count),
            "total_size": int(total_size),
            "orphan_count": int(orphan_count),
            "uploaded_last_7d": int(uploaded_last_7d),
        }
