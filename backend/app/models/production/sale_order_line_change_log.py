from sqlalchemy import Column, DateTime, Integer, String, Index
from sqlalchemy.sql import func

from app.core.database import Base

class SaleOrderLineChangeLog(Base):
    __tablename__ = "sale_order_line_change_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(64), nullable=False, index=True, comment="订单号")
    line_no = Column(String(32), nullable=False, index=True, comment="订单行号")
    change_type = Column(String(32), nullable=False, comment="变更类型: date_changed, qty_changed, cancelled")
    old_value = Column(String(255), nullable=True, comment="旧值")
    new_value = Column(String(255), nullable=True, comment="新值")
    is_processed = Column(Integer, nullable=False, default=0, comment="是否已处理(0:未处理, 1:已处理)")
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    processed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("ix_sale_order_line_change_log_order_line", "order_no", "line_no"),
    )
