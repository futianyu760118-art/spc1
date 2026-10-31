"""文件资产登记表

所有通过 /files/upload 上传的文件统一登记到此表，便于审计、清理孤儿文件、
未来切对象存储统一治理。
"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean
from sqlalchemy.sql import func

from app.core.database import Base


class FileAsset(Base):
    __tablename__ = "file_asset"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(512), nullable=False, unique=True, comment="存储后端内部key")
    url = Column(String(1024), nullable=False, comment="访问URL")
    name = Column(String(512), nullable=False, comment="原始文件名")
    mime = Column(String(128))
    size = Column(BigInteger, nullable=False, default=0, comment="字节大小")

    namespace = Column(String(64), nullable=False, default="misc", index=True, comment="业务域")
    biz_ref = Column(String(128), nullable=True, comment="业务关联标识")

    uploader_id = Column(Integer, nullable=True, index=True)
    uploader_name = Column(String(64), nullable=True)

    ref_count = Column(Integer, nullable=False, default=0)
    is_orphan = Column(Boolean, nullable=False, default=True, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
