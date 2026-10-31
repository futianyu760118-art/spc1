"""物料齐套中心 — 长交期物料注解表模型（改善对策 + 状态，交期数据从PO派生）"""

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class LongLeadMaterial(Base):
    __tablename__ = "long_lead_material"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_code = Column(String(128), index=True)
    supplier_name = Column(String(256), index=True)
    improvement_plan = Column(Text)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
