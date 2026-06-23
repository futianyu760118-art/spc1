from sqlalchemy import Column, DateTime, Integer, Numeric, String, Index
from sqlalchemy.sql import func

from app.core.database import Base

class ProductProcessCapacity(Base):
    __tablename__ = "product_process_capacity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_code = Column(String(64), nullable=False, index=True, comment="产品编码")
    process_type = Column(String(32), nullable=False, comment="工序类型(如: 组装, 包装)")
    upph = Column(Numeric(15, 2), nullable=False, default=0, comment="每小时产能")
    source = Column(String(32), nullable=True, default="OA", comment="数据来源")
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_product_process_capacity_product_process", "product_code", "process_type", unique=True),
    )
