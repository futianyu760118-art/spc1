"""本地文件存储后端

路径规则: {STORAGE_LOCAL_ROOT}/{namespace}/{YYYY}/{MM}/{uuid}{ext}
URL    : {STORAGE_LOCAL_URL_PREFIX}/{key}
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.storage.base import StorageBackend, StoredFile


_SAFE_NS = re.compile(r"^[a-zA-Z0-9_\-]+$")


class LocalStorageBackend(StorageBackend):
    def __init__(self, settings):
        self.root = Path(settings.STORAGE_LOCAL_ROOT).resolve()
        self.url_prefix = settings.STORAGE_LOCAL_URL_PREFIX.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _build_key(self, namespace: str, original_name: str) -> str:
        ns = namespace if _SAFE_NS.match(namespace or "") else "misc"
        now = datetime.now()
        ext = Path(original_name or "").suffix.lower()
        fname = f"{uuid.uuid4().hex}{ext}"
        return f"{ns}/{now:%Y}/{now:%m}/{fname}"

    def _full_path(self, key: str) -> Path:
        # 防穿越
        target = (self.root / key).resolve()
        if not str(target).startswith(str(self.root)):
            raise ValueError(f"Invalid key: {key}")
        return target

    def save(self, content: bytes, original_name: str, mime: str, namespace: str) -> StoredFile:
        key = self._build_key(namespace, original_name)
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return StoredFile(
            key=key,
            url=self.get_url(key),
            name=original_name,
            size=len(content),
            mime=mime,
        )

    def delete(self, key: str) -> None:
        try:
            path = self._full_path(key)
            if path.exists():
                os.remove(path)
        except (FileNotFoundError, ValueError):
            return

    def get_url(self, key: str) -> str:
        return f"{self.url_prefix}/{key}"

    def open(self, key: str) -> BinaryIO:
        return open(self._full_path(key), "rb")

    def mount_static(self, app: FastAPI) -> None:
        # 挂载至 /uploads 静态路由
        app.mount(self.url_prefix, StaticFiles(directory=str(self.root)), name="uploads")
