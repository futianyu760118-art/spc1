"""MRP 域 — 计划建议模型"""

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class MrpSuggestion(Base):
    __tablename__ = "mrp_suggestion"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True, comment="批次ID")
    material_id = Column(Integer, nullable=False, index=True, comment="物料ID(erp_material_id)")
    material_code = Column(String(64), nullable=False, comment="物料编码")
    material_name = Column(String(256), nullable=True, comment="物料名称")
    bill_type = Column(Integer, nullable=False, comment="11010 外购 / 11011 自制 / 11012 委外")
    suggest_qty = Column(Numeric(18, 4), nullable=False, comment="建议量(批量取整后)")
    need_date = Column(Date, nullable=False, comment="需求日")
    action_date = Column(Date, nullable=True, comment="下单/开工/发料日")
    suggested_supplier_id = Column(Integer, nullable=True, comment="默认供应商ID")
    source = Column(String(16), nullable=False, default="demand", server_default="demand", comment="demand 需求缺口 / safety_stock 安全库存")
    is_substitute = Column(Boolean, nullable=False, default=False, server_default=text("false"), comment="替代建议(P3 起)")
    substitute_for_material_id = Column(Integer, nullable=True, comment="替代主料ID(P3 起)")
    status = Column(String(16), nullable=False, default="pending", server_default="pending", index=True, comment="pending/approved/rejected/converted")
    reviewed_by = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    pegging = Column(JSONB, nullable=True, comment="来源订单链")
    compare_status = Column(String(16), nullable=True, comment="match/diff_qty/diff_date/spc_only")
    k3_qty = Column(Numeric(18, 4), nullable=True, comment="K3 对应量")
    k3_need_date = Column(Date, nullable=True, comment="K3 对应需求日")
    converted_target_type = Column(String(32), nullable=True, comment="P2: purchase_requisition")
    converted_target_id = Column(Integer, nullable=True, comment="P2: requisition_line.id")
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
