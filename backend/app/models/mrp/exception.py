"""MRP 域 — 例外消息模型"""

from sqlalchemy import BigInteger, Column, Date, DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class MrpException(Base):
    __tablename__ = "mrp_exception"
    __table_args__ = (
        Index("ix_mrp_exception_run_status", "run_id", "status"),
        Index("ix_mrp_exception_run_material", "run_id", "material_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, comment="批次ID")
    material_id = Column(Integer, nullable=False, comment="物料ID(erp_material_id)")
    material_code = Column(String(64), nullable=False, comment="物料编码")
    material_name = Column(String(256), nullable=True, comment="物料名称")
    exception_code = Column(Integer, nullable=False, comment="金蝶码 6/7/11/15/20/21/50/96")
    exception_type = Column(String(32), nullable=False, comment="past_due_demand/past_due_supply/supply_late/supply_early/supply_excess/no_bom/below_safety_stock")
    source_type = Column(String(32), nullable=False, comment="purchase_order/production_task_order/subcontract_order/transfer_order/purchase_requisition/sale_order_line/mrp_material")
    source_doc_no = Column(String(64), nullable=True, comment="源单据号")
    source_line_no = Column(String(32), nullable=True, comment="源单据行号")
    source_id = Column(Integer, nullable=True, comment="源单据主键(批量动作定位用)")
    need_date = Column(Date, nullable=True, comment="需求日")
    doc_date = Column(Date, nullable=True, comment="单据当前日期")
    adjust_days = Column(Integer, nullable=True, comment="调整天数(建议日期-单据日期，正=延后，负=提前)")
    suggest_date = Column(Date, nullable=True, comment="建议日期")
    suggest_qty = Column(Numeric(18, 4), nullable=True, comment="建议数量/调整量")
    detail = Column(String(512), nullable=True, comment="描述文案")
    pegging = Column(JSONB, nullable=True, comment="来源订单链")
    status = Column(String(16), nullable=False, default="open", server_default="open", comment="open/resolved/ignored")
    handled_by = Column(String(64), nullable=True)
    handled_at = Column(DateTime, nullable=True)
    handle_action = Column(String(32), nullable=True, comment="ignore/reschedule/cancel_reduce/notify")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
