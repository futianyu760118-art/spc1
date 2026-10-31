from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class WritebackQueue(Base):
    __tablename__ = "writeback_queue"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    writeback_type = Column(String(64), nullable=False, index=True)
    business_table = Column(String(128), nullable=False)
    business_pk = Column(String(64), nullable=False)
    target_keys = Column(JSONB, nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, index=True)
    last_error = Column(Text)
    enqueued_by = Column(String(64), nullable=False)
    enqueued_by_user = Column(String(64))
    enqueued_at = Column(DateTime, server_default=func.now(), nullable=False)
    picked_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
