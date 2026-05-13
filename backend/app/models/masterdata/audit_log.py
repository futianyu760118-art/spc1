"""主数据与集成中心 — 审计日志模型"""

from sqlalchemy import BigInteger, Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_table_name", "table_name"),
        Index("ix_audit_log_operator", "operator"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    table_name = Column(String(64), nullable=False)
    record_id = Column(Integer, nullable=False)
    action = Column(String(16), nullable=False)
    field_name = Column(String(64))
    old_value = Column(Text)
    new_value = Column(Text)
    operator = Column(String(64))
    operated_at = Column(DateTime, server_default=func.now(), nullable=False)
