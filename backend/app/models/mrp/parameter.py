"""MRP 域 — 物料级计划参数模型"""

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class MrpParameter(Base):
    __tablename__ = "mrp_parameter"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, nullable=False, unique=True, index=True, comment="物料ID(引用scm_material.erp_material_id)")
    purchase_lead_time_days = Column(Integer, nullable=True, comment="外购固定提前期(天)")
    purchase_variable_lead_time_days = Column(Integer, nullable=True, comment="外购变动提前期(天)")
    purchase_variable_lead_time_batch = Column(Numeric(18, 4), nullable=True, comment="变动提前期批量")
    inspection_lead_time_days = Column(Integer, nullable=True, comment="检验提前期(天)")
    produce_lead_time_days = Column(Integer, nullable=True, comment="自制提前期(天)")
    subcontract_lead_time_days = Column(Integer, nullable=True, comment="委外提前期(天)")
    safety_stock = Column(Numeric(18, 4), nullable=False, default=0, server_default="0", comment="安全库存")
    max_stock = Column(Numeric(18, 4), nullable=True, comment="最高存量(超量判断用)")
    moq = Column(Numeric(18, 4), nullable=True, comment="最小起订量")
    batch_policy = Column(String(20), nullable=False, default="lot_for_lot", server_default="lot_for_lot", comment="批量策略 lot_for_lot/multiple/fixed")
    batch_qty = Column(Numeric(18, 4), nullable=True, comment="批量值(multiple/fixed 生效)")
    default_supplier_id = Column(Integer, nullable=True, comment="默认供应商ID(引用scm_supplier.id)")
    data_source = Column(String(20), nullable=False, default="manual", server_default="manual", comment="manual/excel/erp")
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
