"""S3 / MinIO 对象存储后端（占位）

未来通过 boto3 或 minio-py 实现。当前抛 NotImplementedError，
切换 STORAGE_BACKEND=s3 时需先完成实现。
"""
from __future__ import annotations

from typing import BinaryIO

from app.core.storage.base import StorageBackend, StoredFile


class S3StorageBackend(StorageBackend):
    def __init__(self, settings):
        self.endpoint = getattr(settings, "STORAGE_S3_ENDPOINT", "")
        self.bucket = getattr(settings, "STORAGE_S3_BUCKET", "")
        self.access_key = getattr(settings, "STORAGE_S3_ACCESS_KEY", "")
        self.secret_key = getattr(settings, "STORAGE_S3_SECRET_KEY", "")
        self.region = getattr(settings, "STORAGE_S3_REGION", "")
        # TODO: 初始化 boto3 / minio 客户端

    def save(self, content: bytes, original_name: str, mime: str, namespace: str) -> StoredFile:  # noqa: D401
        raise NotImplementedError("S3StorageBackend.save 尚未实现，请先完成 boto3/minio 集成")

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def get_url(self, key: str) -> str:
        raise NotImplementedError

    def open(self, key: str) -> BinaryIO:
        raise NotImplementedError
