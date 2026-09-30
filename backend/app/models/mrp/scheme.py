"""MRP 域 — 计划方案模型"""

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, text
from sqlalchemy.sql import func

from app.core.database import Base


class MrpScheme(Base):
    __tablename__ = "mrp_scheme"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_code = Column(String(32), nullable=False, unique=True, comment="方案编码，默认 default")
    scheme_name = Column(String(64), nullable=False, comment="方案名称")
    horizon_days = Column(Integer, nullable=False, default=90, server_default="90", comment="计划展望期(天)")
    consider_inventory = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="库存参与供给")
    consider_po = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="采购订单参与供给")
    consider_task = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="生产任务单参与供给")
    consider_subcontract = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="委外订单参与供给")
    consider_transfer = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="调拨在途参与供给")
    consider_requisition = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="采购申请参与供给(P2 起生效)")
    consider_safety_stock = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="安全库存参与净算")
    supply_priority = Column(String(20), nullable=False, default="by_date", server_default="by_date", comment="供给优先顺序 by_date/by_type")
    exception_enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="是否产生例外(P2 起生效)")
    exception_grace_days = Column(Integer, nullable=False, default=3, server_default="3", comment="例外宽限期(自然日)")
    supply_valid_months = Column(Integer, nullable=False, default=6, server_default="6", comment="预计量有效期(月)：供给单据日期早于该窗口不参与运算(对齐K3预计量计算有效期)")
    compare_window_days = Column(Integer, nullable=False, default=3, server_default="3", comment="K3 对比日期窗口(天)")
    compare_qty_threshold_pct = Column(Numeric(5, 2), nullable=False, default=5, server_default="5", comment="K3 对比量差阈值(%)")
    is_default = Column(Boolean, nullable=False, default=False, server_default=text("false"), comment="默认方案")
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="启用")
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
