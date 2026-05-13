"""主数据与集成中心 — 字段映射模型"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class FieldMapping(Base):
    __tablename__ = "field_mapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_system = Column(String(32), nullable=False)
    source_field = Column(String(64), nullable=False)
    target_field = Column(String(64), nullable=False)
    description = Column(String(256))
    created_by = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
