"""生产协同中心 — 生产日报表模型（同步自 ERP/OA 系统）"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Index, text
from sqlalchemy.sql import func

from app.core.database import Base


class ProductionDailyReport(Base):
    __tablename__ = "production_daily_report"

    id = Column(Integer, primary_key=True, autoincrement=True)
    oa_id = Column(String(64), nullable=False, comment="ERP/OA 唯一键(业务主键,用于增量同步去重)")
    report_date = Column(Date, nullable=True, comment="日期")
    sale_order_no = Column(String(64), nullable=True, comment="销售订单号")
    production_order_no = Column(String(64), nullable=True, comment="生产订单号")
    specification = Column(String(128), nullable=True, comment="规格型号")
    bom_no = Column(String(64), nullable=True, comment="BOM编号")
    material_code = Column(String(64), nullable=True, comment="物料代码")
    process = Column(String(64), nullable=True, comment="生产工序")
    color = Column(String(64), nullable=True, comment="颜色")
    completed_qty = Column(Numeric(15, 2), nullable=True, comment="完工数量")
    workshop = Column(String(128), nullable=True, comment="车间")
    work_hours = Column(Numeric(10, 2), nullable=True, comment="当日工时")
    total_wages = Column(Numeric(12, 2), nullable=True, comment="总工资")

    data_source = Column(String(32), nullable=False, server_default="erp", default="erp", comment="数据来源")
    erp_updated_at = Column(DateTime, nullable=True, comment="ERP/OA端更新时间(用于增量同步)")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_production_daily_report_oa_id", "oa_id", unique=True, postgresql_where=text("oa_id IS NOT NULL")),
        Index("ix_production_daily_report_report_date", "report_date"),
        Index("ix_production_daily_report_production_order_no", "production_order_no"),
        Index("ix_production_daily_report_material_code", "material_code"),
        Index("ix_production_daily_report_workshop", "workshop"),
    )
