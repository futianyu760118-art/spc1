"""供应商即时沟通消息模型"""

from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func

from app.core.database import Base


class SupplierMessage(Base):
    __tablename__ = "supplier_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    supplier_name = Column(String(256), nullable=False, index=True)
    supplier_account = Column(String(128), nullable=True)
    sender_id = Column(Integer, ForeignKey("sys_user.id"), nullable=False)
    sender_name = Column(String(128), nullable=False)
    content = Column(Text, nullable=False)
    po_no = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_supplier_message_supplier", "supplier_name", "created_at"),
    )