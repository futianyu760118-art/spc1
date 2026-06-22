"""物料齐套中心 — K3 MRP计划订单模型"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class MrpPlanOrder(Base):
    __tablename__ = "mrp_plan_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fbill_no = Column(String(64), nullable=False, comment='计划订单号')
    fmaterial_id = Column(Integer, nullable=True, comment='物料内码')
    material_code = Column(String(64), nullable=False, comment='物料代码')
    material_name = Column(String(256), nullable=True, comment='物料名称')
    fplan_qty = Column(Numeric(15, 2), nullable=True, comment='计划数量')
    fplan_start_date = Column(Date, nullable=True, comment='计划开始日期')
    fplan_finish_date = Column(Date, nullable=True, comment='计划完工日期')
    fneed_date = Column(Date, nullable=True, comment='需求日期')
    forder_type = Column(String(32), nullable=True, comment='订单类型(采购/生产/委外)')
    fstatus = Column(Integer, nullable=False, comment='状态(0=计划,1=已下达,2=已关闭,3=已作废)')
    fsupply_org = Column(String(128), nullable=True, comment='供应组织')
    frequire_org = Column(String(128), nullable=True, comment='需求组织')
    fsource_bill_no = Column(String(64), nullable=True, comment='源单号')
    data_source = Column(String(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('fbill_no', name='uq_mrp_plan_order_fbill_no'),
    )
