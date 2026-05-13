"""生产协同中心 — 工序进度统一模型（前道/贴片/精益/组装/包装）"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, Index
from sqlalchemy.sql import func

from app.core.database import Base


class ProcessProgress(Base):
    __tablename__ = "process_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_type = Column(String(16), nullable=False, index=True)
    # --- 通用字段 ---
    seq_no = Column(Integer)
    plan_date = Column(Date, index=True)
    order_no = Column(String(64), index=True)
    product_code = Column(String(64), index=True)
    line_no = Column(String(32))
    model_code = Column(String(128))
    color_spec = Column(String(128))
    qty = Column(Numeric(15, 2))
    planned_qty = Column(Numeric(15, 2))
    kit_qty = Column(Numeric(15, 2))
    online_date = Column(Date)
    daily_plan_qty = Column(Numeric(15, 2))
    daily_complete_qty = Column(Numeric(15, 2))
    completion_rate = Column(String(16))
    work_hours = Column(Numeric(6, 1))
    remark = Column(Text)
    # --- 前道(4.1)特有 ---
    customer_code = Column(String(64))
    sale_order_no = Column(String(64))
    order_date = Column(String(32))
    by_style = Column(Integer)
    shell_status = Column(String(64))
    frame_status = Column(String(64))
    handle_status = Column(String(64))
    bracket_status = Column(String(64))
    product_name = Column(String(256))
    delivery_date = Column(Date)
    # --- 贴片(4.2)特有 ---
    material_long_code = Column(String(128))
    material_name = Column(String(256))
    material_confirm = Column(String(64))
    unit_price = Column(Numeric(15, 4))
    daily_amount = Column(Numeric(15, 2))
    complete_time = Column(String(64))
    hour_capacity = Column(Numeric(15, 2))
    demand_time = Column(String(64))
    total_plan_complete = Column(Numeric(15, 2))
    # --- 精益(4.3)特有 ---
    next_process = Column(String(128))
    # --- 组装/包装(4.4/4.5)特有 ---
    assembly_group = Column(String(64))
    warehouse_in_qty = Column(Numeric(15, 2))
    # --- 状态 ---
    status = Column(String(32), nullable=False, default='pending')
    data_source = Column(String(32))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_process_order_product', 'order_no', 'product_code'),
    )
