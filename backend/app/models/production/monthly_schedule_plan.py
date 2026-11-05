"""月度排产方案（独立于原排产计划，供新规则使用）。"""
from sqlalchemy import Boolean, Column, Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class MonthlySchedulePlan(Base):
    __tablename__ = "monthly_schedule_plan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_month = Column(String(7), nullable=False, index=True, comment="排产月份 YYYY-MM")
    batch_no = Column(String(64), nullable=True, index=True, comment="生成批次")
    order_no = Column(String(64), nullable=False, index=True)
    line_no = Column(String(32), nullable=False)
    product_code = Column(String(64), nullable=True)
    product_name = Column(String(256), nullable=True)
    bom_no = Column(String(64), nullable=True, index=True)
    department = Column(String(64), nullable=True)
    schedule_bucket = Column(String(32), nullable=False, index=True)
    quantity = Column(Numeric(15, 2), nullable=False, default=0, comment="当天排产数量")
    upph = Column(Numeric(15, 2), nullable=False, default=0)
    manpower = Column(Integer, nullable=False, default=10)
    daily_work_hours = Column(Numeric(8, 2), nullable=False, default=12)
    plan_date = Column(Date, nullable=False, index=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    source_order_qty = Column(Numeric(15, 2), nullable=True)
    source_promised_date = Column(Date, nullable=True)
    price_total = Column(Numeric(15, 4), nullable=True, comment="阶段单价合计")
    status = Column(String(32), nullable=False, default="planned", index=True)
    remark = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_monthly_schedule_plan_month_bucket_date", "schedule_month", "schedule_bucket", "plan_date"),
        Index("ix_monthly_schedule_plan_order_line", "order_no", "line_no"),
    )
