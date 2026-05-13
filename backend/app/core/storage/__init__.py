"""文件存储抽象层

统一接口，支持本地存储（默认）和 S3/MinIO（占位，未来实现）。
业务代码只调 get_storage()，切换后端零代码改动。
"""
from functools import lru_cache

from app.core.config import get_settings
from app.core.storage.base import StorageBackend, StoredFile
from app.core.storage.local import LocalStorageBackend


@lru_cache
def get_storage() -> StorageBackend:
    settings = get_settings()
    backend = (settings.STORAGE_BACKEND or "local").lower()
    if backend == "s3":
        from app.core.storage.s3 import S3StorageBackend
        return S3StorageBackend(settings)
    return LocalStorageBackend(settings)


__all__ = ["StorageBackend", "StoredFile", "get_storage"]
