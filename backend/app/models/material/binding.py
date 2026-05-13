"""物料齐套中心 — 订单-物料-PO绑定模型"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class OrderMaterialPoBinding(Base):
    __tablename__ = "order_material_po_binding"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(64), nullable=False, index=True)
    line_no = Column(String(32), nullable=False)
    material_code = Column(String(64), nullable=False, index=True)
    po_no = Column(String(64), ForeignKey('purchase_order.po_no'))
    purchase_order = relationship('PurchaseOrder', lazy='raise')
    bound_qty = Column(Numeric(15, 2))
    bind_status = Column(String(32), nullable=False)
    bind_source = Column(String(32), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
