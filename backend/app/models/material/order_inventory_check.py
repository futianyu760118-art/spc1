"""物料齐套中心 — 订单物料盘点记录模型"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class OrderInventoryCheck(Base):
    __tablename__ = "scm_order_inventory_check"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(64), nullable=False, index=True)
    checked_by = Column(String(100))
    checked_at = Column(DateTime, server_default=func.now(), nullable=False)
    total_materials = Column(Integer)
    received_materials = Column(Integer)
    partial_received_materials = Column(Integer)
    not_ordered_materials = Column(Integer)
    overdue_materials = Column(Integer)
    kit_rate = Column(Numeric(5, 4))
    materials_snapshot = Column(JSONB)
    note = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
