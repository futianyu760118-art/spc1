"""物料齐套中心 — 收货批次模型"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class ReceiptBatch(Base):
    __tablename__ = "receipt_batch"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_no = Column(String(64), nullable=False, index=True)
    po_no = Column(String(64))
    material_code = Column(String(64))
    received_qty = Column(Numeric(15, 2))
    receipt_date = Column(Date)
    quality_status = Column(String(32), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
