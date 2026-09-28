"""MRP 域 — 运算批次模型"""

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class MrpRun(Base):
    __tablename__ = "mrp_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_no = Column(String(32), nullable=False, unique=True, comment="批次号 MRPRUN-YYYYMMDD-NNN")
    run_type = Column(String(16), nullable=False, default="manual", server_default="manual", comment="scheduled/manual")
    triggered_by = Column(String(64), nullable=True, comment="触发人")
    scheme_id = Column(Integer, nullable=True, comment="计划方案ID")
    scheme_snapshot = Column(JSONB, nullable=True, comment="方案与参数解析快照(含回退统计)")
    status = Column(String(16), nullable=False, default="running", server_default="running", index=True, comment="running/success/failed")
    horizon_days = Column(Integer, nullable=False, default=90, server_default="90", comment="本次展望期")
    stats = Column(JSONB, nullable=True, comment="统计:订单/物料/建议/耗时/数据体检")
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
