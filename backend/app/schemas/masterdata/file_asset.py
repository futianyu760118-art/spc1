"""文件资产 schemas"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class FileAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    url: str
    name: str
    mime: Optional[str] = None
    size: int = 0
    namespace: str
    biz_ref: Optional[str] = None
    uploader_id: Optional[int] = None
    uploader_name: Optional[str] = None
    ref_count: int = 0
    is_orphan: bool = True
    uploaded_at: Optional[datetime] = None


class FileAssetListOut(BaseModel):
    items: List[FileAssetOut]
    total: int
    page: int
    page_size: int


class FileStatsOut(BaseModel):
    total_count: int = 0
    total_size: int = 0  # 字节
    orphan_count: int = 0
    uploaded_last_7d: int = 0
