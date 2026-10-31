"""生产协同中心 — 工价审核数据模型（同步自 ERP 系统）"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Index, text
from sqlalchemy.sql import func

from app.core.database import Base


class ProductionLaborPriceAudit(Base):
    __tablename__ = "production_labor_price_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    oa_id = Column(String(64), nullable=True, comment="ERP/OA 唯一键(业务主键)")
    doc_no = Column(String(64), nullable=True, comment="单据编号")
    apply_date = Column(Date, nullable=True, comment="申请日期")
    valid_flag = Column(Integer, nullable=True, comment="有效标志")
    department_id = Column(Integer, nullable=True, comment="部门ID")
    material_id = Column(Integer, nullable=True, comment="物料ID(引用scm_material.erp_material_id)")
    material_code = Column(String(64), nullable=True, comment="物料代码")
    labor_price_code = Column(String(64), nullable=True, comment="工价表唯一码(业务主键,用于增量同步去重)")
    labor_price_amount = Column(Numeric(15, 4), nullable=True, comment="工价金额")
    bom_id = Column(Integer, nullable=True, comment="BOM ID")
    bom_code = Column(String(64), nullable=True, comment="BOM编码")

    data_source = Column(String(32), nullable=False, server_default="erp", default="erp", comment="数据来源")
    erp_updated_at = Column(DateTime, nullable=True, comment="ERP端更新时间(用于增量同步)")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "uq_production_labor_price_audit_code",
            "labor_price_code",
            unique=True,
            postgresql_where=text("labor_price_code IS NOT NULL"),
        ),
        Index("ix_production_labor_price_audit_apply_date", "apply_date"),
        Index(
            "uq_production_labor_price_audit_oa_id",
            "oa_id",
            unique=True,
            postgresql_where=text("oa_id IS NOT NULL"),
        ),
        Index("ix_production_labor_price_audit_material_code", "material_code"),
        Index("ix_production_labor_price_audit_department_id", "department_id"),
    )
