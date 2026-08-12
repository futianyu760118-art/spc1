"""物料齐套中心 — 采购订单/采购到料计划统一模型"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_no = Column(String(64), nullable=False, index=True)
    detail_id = Column(Integer, nullable=False, default=1)
    material_code = Column(String(64), nullable=False, index=True)
    supplier_code = Column(String(64))
    supplier_name = Column(String(256))
    supplier_account = Column(String(128))
    material_type_name = Column(String(64))
    material_property = Column(Integer)
    material_name = Column(String(256))
    po_qty = Column(Numeric(15, 2))
    po_price = Column(Numeric(15, 4))
    po_date = Column(Date)
    po_status = Column(String(32), nullable=False)
    eta = Column(Date)
    original_eta = Column(Date)
    actual_arrival_date = Column(Date)
    owner = Column(String(64))
    owner_id = Column(Integer, ForeignKey("sys_user.id"), nullable=True, index=True)
    remark = Column(Text)
    data_source = Column(String(32))
    # --- CSV采购到料计划扩展字段 ---
    order_no = Column(String(64), index=True)
    spec_model = Column(String(256))
    unit = Column(String(32))
    received_qty = Column(Numeric(15, 2))
    arrival_hour_note = Column(String(256))
    inspection_date = Column(Date)
    is_closed = Column(Integer, nullable=False, server_default='0', default=0)
    last_writeback_at = Column(DateTime, nullable=True, comment="最近一次成功回写时间")
    last_writeback_status = Column(String(16), nullable=True, comment="success/failed,列表页展示用")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('po_no', 'detail_id', name='uq_purchase_order_po_no_detail_id'),
    )
