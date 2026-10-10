"""存储后端抽象基类"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO, Optional


@dataclass
class StoredFile:
    """存储后端返回的统一文件描述符"""
    key: str  # 后端内部 key（本地: namespace/yyyy/mm/uuid.ext, S3: object key）
    url: str  # 访问 URL（本地直链 / S3 预签名）
    name: str  # 原始文件名
    size: int  # 字节大小
    mime: str  # MIME type

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "url": self.url,
            "name": self.name,
            "size": self.size,
            "mime": self.mime,
        }


class StorageBackend(ABC):
    """所有存储后端共享接口

    子类 __init__ 必须设置 self.url_prefix（get_url 依赖）。
    """

    @abstractmethod
    def save(self, content: bytes, original_name: str, mime: str, namespace: str) -> StoredFile:
        """保存文件，返回 StoredFile（含 key/url 等）"""

    @abstractmethod
    def delete(self, key: str) -> None:
        """按 key 删除文件，幂等（不存在不报错）"""

    def get_url(self, key: str) -> str:
        """可访问 URL：{url_prefix}/{key}（本地直链 / S3 经代理路由转发）"""
        return f"{self.url_prefix}/{key}"

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """打开文件用于流式读取（鉴权下载场景）"""

    def mount_static(self, app) -> None:  # noqa: D401
        """可选：将存储目录挂载到 FastAPI 静态路由（仅本地后端使用）"""
        return None
