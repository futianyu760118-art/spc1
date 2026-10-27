"""OA 返工单（品质异常流程 formtable_main_23）本地快照."""

from sqlalchemy import Column, Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ProductionReworkOrder(Base):
    __tablename__ = "production_rework_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(32), nullable=False, unique=True, index=True, comment="OA requestId")
    form_id = Column(Integer, nullable=True, comment="OA formtable_main_23.id")
    flow_no = Column(String(64), nullable=True, index=True, comment="OA 流程编号 lcbh")
    apply_date = Column(Date, nullable=True, index=True, comment="申请日期 sqrq")
    flow_type = Column(Integer, nullable=True, comment="流程类型 lclx: 0制程/1外购来料/2出货/4其他")
    order_no = Column(String(64), nullable=True, index=True, comment="订单号 ddh")
    product_code = Column(String(128), nullable=True, index=True, comment="产品编码 cpbhlh")
    product_name = Column(Text, nullable=True, comment="产品名称 cpmclm")
    production_task_no = Column(String(64), nullable=True, comment="生产任务单号 scrwdh")
    batch_qty = Column(Integer, nullable=True, comment="批量数 pls")
    sample_qty = Column(Integer, nullable=True, comment="抽样数 cys")
    defect_qty = Column(Integer, nullable=True, comment="不良数 bls")
    rework_hours = Column(Numeric(15, 2), nullable=True, comment="返工工时 rggss")
    hour_price = Column(Numeric(15, 2), nullable=True, comment="工时单价 gsdj")
    hour_cost = Column(Numeric(15, 2), nullable=True, comment="工时费用 gsfy")
    total_cost = Column(Numeric(15, 2), nullable=True, comment="总费用 zjfy")
    is_rework = Column(Integer, nullable=True, comment="是否返工 sffg")
    approve_flag = Column(Integer, nullable=True, comment="是否审批 sfsp")
    execute_status = Column(String(64), nullable=True, comment="执行情况 zxqk")
    flow_status = Column(Integer, nullable=True, comment="流程状态 currentnodetype")
    title = Column(Text, nullable=True, comment="流程标题 bt")
    synced_at = Column(DateTime, server_default=func.now(), nullable=False, comment="同步时间")

    __table_args__ = (
        Index("ix_prod_rework_order_apply", "apply_date", "order_no"),
        Index("ix_prod_rework_order_product", "product_code", "apply_date"),
    )
