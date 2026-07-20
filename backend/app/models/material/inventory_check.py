"""物料齐套中心 — 物料盘点单模型（盘点单头 + 物料行）"""

from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, DateTime, Date, Text,
    UniqueConstraint, Index, ForeignKey,
)
from sqlalchemy.sql import func

from app.core.database import Base


class StockCheck(Base):
    __tablename__ = "scm_inventory_check"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    check_no = Column(String(32), nullable=False, unique=True, comment="盘点单号 PDyyyyMMdd-NNN")
    order_no = Column(String(64), nullable=True, index=True, comment="触发起源订单号(manual 类型可空)")
    title = Column(String(200), nullable=True, comment="盘点单标题")
    check_type = Column(String(16), nullable=False, default="order", comment="order/manual/cycle_count")
    status = Column(String(16), nullable=False, default="open", comment="open/in_progress/completed/cancelled")
    check_date = Column(Date, nullable=False, comment="盘点日期")
    total_materials = Column(Integer, nullable=False, default=0, comment="应盘物料数")
    checked_materials = Column(Integer, nullable=False, default=0, comment="已盘物料数")
    total_diff_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="总差异数")
    created_by = Column(String(100), nullable=True)
    checked_by = Column(String(100), nullable=True, comment="完工人")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    remark = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_scm_inventory_check_order_date", "order_no", "check_date"),
    )


class StockCheckItem(Base):
    __tablename__ = "scm_inventory_check_item"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    check_id = Column(BigInteger, ForeignKey("scm_inventory_check.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no = Column(String(32), nullable=True, comment="关联 SaleOrderLine 行号(跨行聚合行时为空)")
    material_id = Column(BigInteger, nullable=True, index=True, comment="物料ID")
    material_code = Column(String(50), nullable=True)
    material_name = Column(String(200), nullable=True)
    spec_model = Column(String(200), nullable=True)
    unit = Column(String(20), nullable=True)
    req_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="应盘数(BOM standard_qty × order_qty)")
    system_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="库存数(快照)")
    actual_qty = Column(Numeric(18, 4), nullable=True, comment="盘点数(用户录入)")
    diff_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="差异数=actual-system")
    is_checked = Column(Integer, nullable=False, default=0, comment="盘点标记 0否1是")
    checked_at = Column(DateTime, nullable=True)
    checked_by = Column(String(100), nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("check_id", "material_id", "line_no", name="uq_stock_check_item"),
    )
