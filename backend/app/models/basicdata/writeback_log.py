from sqlalchemy import Column, BigInteger, String, Text, DateTime, Integer
from sqlalchemy.sql import func

from app.core.database import Base


class WritebackLog(Base):
    __tablename__ = "writeback_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(String(36), nullable=False, unique=True)
    queue_id = Column(BigInteger)
    writeback_type = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)
    sql_executed = Column(Text)
    rows_affected = Column(Integer)
    duration_ms = Column(Integer)
    error_detail = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
