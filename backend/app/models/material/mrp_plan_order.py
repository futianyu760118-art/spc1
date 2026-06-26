"""物料齐套中心 — MRP计划订单模型"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, PrimaryKeyConstraint, Index
from sqlalchemy.sql import func

from app.core.database import Base


class MrpPlanOrder(Base):
    """MRP计划订单 — 销售订单ID + 物料ID 联合主键"""
    __tablename__ = "mrp_plan_order"

    sale_order_id = Column(Integer, nullable=False, comment='销售订单ID')
    material_id = Column(String(50), nullable=False, comment='物料ID')
    sale_order_no = Column(String(64), nullable=True, comment='销售订单号')
    material_code = Column(String(64), nullable=False, comment='物料代码')
    material_name = Column(String(256), nullable=True, comment='物料名称')
    material_property = Column(Integer, nullable=True, comment='物料属性 1-外购 2-自制 3-委外加工 5-虚拟件 6-特征类 7-配置类 8-规划类 9-组装件')
    material_type = Column(String(64), nullable=True, comment='物料类型')
    unit_id = Column(String(50), nullable=True, comment='单位ID')
    unit_name = Column(String(64), nullable=True, comment='单位名称')
    base_plan_qty = Column(Numeric(15, 2), nullable=True, comment='基本单位计划订单量')
    mrp_run_time = Column(DateTime, nullable=True, comment='MRP运算时间')
    need_date = Column(Date, nullable=True, comment='需求日期')
    is_closed = Column(Integer, nullable=False, server_default='0', default=0, comment='业务关闭状态 1-已关闭 0-未关闭')
    close_type = Column(Integer, nullable=True, comment='关闭类型 0-投放关闭')
    bill_type = Column(Integer, nullable=True, comment='单据类型 11010-采购申请 11011-自制生产任务单 11012-委外申请')
    stock_qty = Column(Numeric(15, 2), nullable=True, comment='库存数量')
    audit_date = Column(Date, nullable=True, comment='审核日期')
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('sale_order_id', 'material_id', name='pk_mrp_plan_order'),
        Index('ix_mrp_plan_order_material_code', 'material_code'),
        Index('ix_mrp_plan_order_sale_order_no', 'sale_order_no'),
    )
