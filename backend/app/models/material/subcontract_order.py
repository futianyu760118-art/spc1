"""物料齐套中心 — 委外订单模型（同步自 ERP K3）"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class SubcontractOrder(Base):
    __tablename__ = "subcontract_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    erp_order_id = Column(Integer, nullable=True, index=True, comment="委外订单ID (ERP FID)")
    bill_no = Column(String(64), nullable=False, unique=True, index=True, comment="单据编号")
    bill_date = Column(Date, nullable=True, comment="日期")
    bill_type = Column(String(64), nullable=True, comment="类型")
    settlement_method = Column(String(64), nullable=True, comment="结算方式")
    settle_date = Column(Date, nullable=True, comment="结算日期")
    supplier_id = Column(Integer, nullable=True, comment="供应商id")
    department_id = Column(Integer, nullable=True, comment="部门id")
    salesman_id = Column(Integer, nullable=True, comment="业务员id")
    manager_id = Column(Integer, nullable=True, comment="主管id")
    auditor_id = Column(Integer, nullable=True, comment="审核人id")
    audit_date = Column(Date, nullable=True, comment="审核日期")
    creator_id = Column(Integer, nullable=True, comment="制单人id")
    remark = Column(Text, nullable=True, comment="摘要")
    voided_flag = Column(Integer, nullable=True, comment="作废标志 0/1")
    closed_flag = Column(Integer, nullable=True, comment="关闭标志 0/1")
    status = Column(String(32), nullable=True, comment="状态")
    bill_type_id = Column(Integer, nullable=True, comment="单据类型id")
    rejected_flag = Column(Integer, nullable=True, comment="拒单标识 0/1")
    close_date = Column(Date, nullable=True, comment="关闭日期")
    plan_category = Column(Integer, nullable=True, comment="计划类别")
    closer_id = Column(Integer, nullable=True, comment="关闭人id")
    erp_updated_at = Column(DateTime, nullable=True, comment="修改时间(增量同步用)")
    data_source = Column(String(32), nullable=True, comment="数据来源")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
