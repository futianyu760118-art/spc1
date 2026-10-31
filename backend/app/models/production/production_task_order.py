"""生产协同中心 — OA 生产任务单模型（同步自 OA 系统）"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Index, text
from sqlalchemy.sql import func

from app.core.database import Base


class ProductionTaskOrder(Base):
    __tablename__ = "production_task_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=True, comment="OA 任务单ID")
    task_no = Column(String(64), nullable=True, comment="任务单号")
    workshop = Column(String(128), nullable=True, comment="生产车间")
    material_code = Column(String(64), nullable=True, comment="物料代码")
    material_name = Column(String(256), nullable=True, comment="物料名称")
    planned_start_date = Column(Date, nullable=True, comment="计划开工日期")
    planned_end_date = Column(Date, nullable=True, comment="计划完工日期")
    actual_start_date = Column(Date, nullable=True, comment="实际开工日期")
    actual_end_date = Column(Date, nullable=True, comment="实际完工日期")
    task_qty = Column(Numeric(15, 2), nullable=True, comment="任务单数量")
    repair_qty = Column(Numeric(15, 2), nullable=True, comment="返修数量")
    actual_qty = Column(Numeric(15, 2), nullable=True, comment="实做数量")
    task_type = Column(String(64), nullable=True, comment="类型")
    sale_order_no = Column(String(64), nullable=True, comment="销售订单号")
    sale_order_id = Column(Integer, nullable=True, comment="销售订单ID (ERP FOrderInterID)")
    bom_id = Column(Integer, nullable=True, comment="BOM ID")
    start_flag = Column(Integer, nullable=True, comment="开工标志 0/1")
    is_closed = Column(Integer, nullable=True, comment="是否关闭 0-未关闭 1-已关闭")
    audit_status = Column(Integer, nullable=True, comment="审核状态 0-未审核 1-已审核")
    mrp_flag = Column(Integer, nullable=True, comment="MRP标志 0/1")
    audit_user_id = Column(Integer, nullable=True, comment="审核人ID")
    request_user_id = Column(Integer, nullable=True, comment="请求人ID")
    supplier_id = Column(Integer, nullable=True, comment="供应商ID")

    data_source = Column(String(32), nullable=False, server_default="oa", default="oa", comment="数据来源")
    erp_updated_at = Column(DateTime, nullable=True, comment="OA端更新时间(用于增量同步)")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_production_task_order_task_id", "task_id", unique=True, postgresql_where=text("task_id IS NOT NULL")),
        Index("ix_production_task_order_task_no", "task_no"),
        Index("ix_production_task_order_material_code", "material_code"),
        Index("ix_production_task_order_sale_order_no", "sale_order_no"),
        Index("ix_production_task_order_sale_order_id", "sale_order_id"),
    )
