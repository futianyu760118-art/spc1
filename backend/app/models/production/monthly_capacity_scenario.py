"""月度产能规划全局场景参数（单行配置）。"""

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String
from sqlalchemy.sql import func

from app.core.database import Base


class MonthlyCapacityScenario(Base):
    __tablename__ = "monthly_capacity_scenario"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workdays = Column(Integer, nullable=False, default=26)
    daily_hours = Column(Numeric(5, 2), nullable=False, default=12)
    assembly_manpower = Column(Integer, nullable=False, default=12)
    packaging_manpower = Column(Integer, nullable=False, default=9)
    lean_manpower = Column(Integer, nullable=False, default=4)
    include_sunday = Column(Boolean, nullable=False, default=False)
    include_scheduled = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
