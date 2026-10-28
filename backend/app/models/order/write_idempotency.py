"""订单受控写操作的幂等记录。"""

from sqlalchemy import BigInteger, Column, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class OrderWriteIdempotency(Base):
    __tablename__ = "order_write_idempotency"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    request_hash = Column(String(64), nullable=False)
    operation = Column(String(64), nullable=False)
    order_no = Column(String(64), nullable=False)
    result_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_order_write_idempotency_created_at", "created_at"),
    )
