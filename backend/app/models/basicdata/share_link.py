"""基础数据与集成中心 — 页面分享链接模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class ShareLink(Base):
    __tablename__ = "share_link"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), nullable=False, unique=True, index=True, comment="分享唯一标识")
    target_path = Column(String(512), nullable=False, comment="目标页面路径")
    target_params = Column(JSONB, nullable=True, comment="额外参数")
    permissions = Column(JSONB, nullable=True, comment="分享权限，如 ['read','create','update','delete']")
    reason = Column(String(256), nullable=True, comment="分享原因")
    created_by = Column(Integer, nullable=False, comment="创建人 user_id")
    expires_at = Column(DateTime(timezone=True), nullable=True, comment="过期时间，null 表示永久")
    is_revoked = Column(Boolean, nullable=False, default=False, comment="是否已撤销")
    access_count = Column(Integer, nullable=False, default=0, comment="访问次数")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
