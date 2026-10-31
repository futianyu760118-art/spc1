"""物料齐套中心 — 物料需求模型"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean, Index, Text
from sqlalchemy.sql import func

from app.core.database import Base


class MaterialDemand(Base):
    __tablename__ = "material_demand"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(64), nullable=False, index=True)
    line_no = Column(String(32), nullable=False)
    material_code = Column(String(64), nullable=False, index=True)
    material_name = Column(String(256))
    material_property = Column(Integer)
    material_type_name = Column(String(64))
    spec_model = Column(String(256))
    unit = Column(String(32))
    req_qty = Column(Numeric(15, 2))
    req_date = Column(Date)
    allocated_qty = Column(Numeric(15, 2), nullable=False, default=0)
    shortage_qty = Column(Numeric(15, 2), nullable=False, default=0)
    shortage_flag = Column(Boolean, nullable=False, default=False)
    data_source = Column(String(32))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
