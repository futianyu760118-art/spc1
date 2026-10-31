"""订单交付中心 — 跑单管理模型（对齐2.跑单CSV 19列）"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, Boolean, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class RunOrder(Base):
    """跑单管理 — 对齐 2.跑单 CSV 列"""
    __tablename__ = "run_order"
    __table_args__ = (
        UniqueConstraint("order_no", name="uq_run_order"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_code = Column(String(64), index=True, comment="客户代码")
    order_no = Column(String(64), nullable=False, index=True, comment="订单号")
    order_qty = Column(Numeric(15, 2), comment="数量")
    order_type = Column(String(32), comment="订单性质: 返单/新订单/补单/配件")
    contract_date = Column(Date, comment="合同日期")
    delivery_date = Column(Date, comment="交付日期")
    run_date = Column(Date, comment="跑单日期")
    run_days = Column(Integer, comment="跑单时间(天)")
    order_amount = Column(Numeric(15, 2), comment="订单金额")
    packaging_not_released = Column(Text, comment="包材未投放")
    po_placed_date = Column(Date, comment="下单时间")
    material_ready_date = Column(Date, comment="齐套时间")
    procurement_cycle = Column(Integer, comment="采购周期(天)")
    completed_date = Column(Date, comment="完成日期")
    shipped_date = Column(Date, comment="发货日期")
    order_status = Column(String(32), comment="订单状态")
    delay_reason = Column(Text, comment="未及时原因分析")
    remark = Column(Text, comment="备注")
    is_domestic = Column(Boolean, default=False, comment="是否内销跑单")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
