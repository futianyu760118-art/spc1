"""S3 / MinIO 对象存储后端

文件保存在 MinIO 桶，key 与本地后端同构（{namespace}/{YYYY}/{MM}/{uuid}{ext}）。
访问 URL 保持 /uploads/{key} 形状：mount_static 挂载的代理路由从 MinIO 流式转发，
FileAsset 表已存 URL 与前端 <img>/<iframe> 引用零改动。
"""
from __future__ import annotations

import io
from typing import BinaryIO
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from minio import Minio
from minio.error import S3Error
from starlette.concurrency import run_in_threadpool

from app.core.storage.base import StorageBackend, StoredFile
from app.core.storage.keys import build_storage_key
from app.core.storage.security import SECURITY_HEADERS

_PROXY_CHUNK = 64 * 1024


class S3StorageBackend(StorageBackend):
    def __init__(self, settings):
        endpoint = (settings.STORAGE_S3_ENDPOINT or "").strip()
        if not endpoint:
            raise RuntimeError("STORAGE_S3_ENDPOINT 未配置，无法启用 S3 存储")
        self.bucket = (settings.STORAGE_S3_BUCKET or "spc-files").strip()
        self.url_prefix = settings.STORAGE_LOCAL_URL_PREFIX.rstrip("/")
        self.client = Minio(
            endpoint,
            access_key=settings.STORAGE_S3_ACCESS_KEY,
            secret_key=settings.STORAGE_S3_SECRET_KEY,
            secure=bool(settings.STORAGE_S3_SECURE),
            region=settings.STORAGE_S3_REGION or None,
        )
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def save(self, content: bytes, original_name: str, mime: str, namespace: str) -> StoredFile:
        key = build_storage_key(namespace, original_name)
        data = io.BytesIO(content)
        self.client.put_object(
            self.bucket,
            key,
            data,
            length=len(content),
            content_type=mime or "application/octet-stream",
            # S3 用户元数据经 HTTP 头传输，只允许 US-ASCII；原始文件名可能含
            # 中文等非 ASCII 字符（如"屏幕截图 xxx.png"），直接传会抛
            # ValueError: unsupported metadata value ...；百分号编码后恒为 ASCII。
            metadata={"original-name": quote(original_name or "unnamed", safe="")[:256]},
        )
        return StoredFile(
            key=key,
            url=self.get_url(key),
            name=original_name or "unnamed",
            size=len(content),
            mime=mime,
        )

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except S3Error as exc:
            if exc.code != "NoSuchKey":
                raise

    def open(self, key: str) -> BinaryIO:
        try:
            return self.client.get_object(self.bucket, key)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                raise FileNotFoundError(key) from None
            raise

    def mount_static(self, app: FastAPI) -> None:
        # /uploads 代理路由：GET 流式转发 MinIO 对象（MinIO 调用在线程池执行，不阻塞事件循环）。
        # 与本地静态挂载同构的安全头，阻止可疑附件同源渲染执行。
        storage = self

        @app.get(self.url_prefix + "/{key:path}", include_in_schema=False, name="uploads-proxy")
        async def serve_upload(key: str):
            try:
                obj = await run_in_threadpool(storage.client.get_object, storage.bucket, key)
            except S3Error as exc:
                if exc.code == "NoSuchKey":
                    raise HTTPException(status_code=404, detail="文件不存在")
                raise HTTPException(status_code=502, detail="对象存储不可用")

            def _iter():
                try:
                    while True:
                        chunk = obj.read(_PROXY_CHUNK)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    obj.close()
                    obj.release_conn()

            headers = {k: v for k, v in SECURITY_HEADERS}
            return StreamingResponse(
                _iter(),
                media_type=(obj.headers or {}).get("content-type") or "application/octet-stream",
                headers=headers,
            )
