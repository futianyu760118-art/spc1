"""Production schedule plan ledger."""

from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text, Index
from sqlalchemy.sql import func

from app.core.database import Base


class ProductionSchedulePlan(Base):
    __tablename__ = "production_schedule_plan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department = Column(String(32), nullable=False, index=True)
    plan_date = Column(Date, nullable=False, index=True)
    order_no = Column(String(64), nullable=True, index=True)
    product_code = Column(String(64), nullable=True, index=True)
    model_code = Column(String(128), nullable=True)
    quantity = Column(Numeric(15, 2), nullable=True)
    owner = Column(String(64), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    priority = Column(String(32), nullable=False, default="normal")
    status = Column(String(32), nullable=False, default="planned", index=True)
    remark = Column(Text, nullable=True)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_production_schedule_dept_date", "department", "plan_date"),
        Index("ix_production_schedule_order_product", "order_no", "product_code"),
    )
