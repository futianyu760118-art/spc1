"""备份管理 — 备份记录与定时配置模型"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class BackupRecord(Base):
    __tablename__ = "backup_record"
    __table_args__ = (
        Index("ix_backup_record_created", "created_at"),
        UniqueConstraint("record_name", name="uq_backup_record_name"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    record_name = Column(String(32), nullable=False, comment="戳名 YYYYmmdd_HHMMSS，双文件名前缀")
    db_file = Column(String(128), nullable=False)
    uploads_file = Column(String(128), nullable=False)
    db_size = Column(BigInteger, nullable=False, default=0)
    uploads_size = Column(BigInteger, nullable=False, default=0)
    db_sha256 = Column(String(64), nullable=True)
    uploads_sha256 = Column(String(64), nullable=True)
    source = Column(String(16), nullable=False, default="manual", comment="manual/scheduled/safety")
    status = Column(String(16), nullable=False, default="running", comment="running/success/failed/deleted")
    duration_seconds = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_by = Column(BigInteger, nullable=True, comment="sys_user.id，定时/safety 为空")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class BackupConfig(Base):
    __tablename__ = "backup_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enabled = Column(Boolean, nullable=False, default=False)
    frequency = Column(String(16), nullable=False, default="daily", comment="daily/weekly")
    schedule_time = Column(String(5), nullable=False, default="03:30")
    weekday = Column(Integer, nullable=False, default=1, comment="1=周一 ... 7=周日，weekly 时有效")
    retention_count = Column(Integer, nullable=False, default=7)
    last_triggered_at = Column(DateTime, nullable=True)
    updated_by = Column(BigInteger, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
