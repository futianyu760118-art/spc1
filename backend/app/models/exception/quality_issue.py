"""异常与质量中心 — 品质异常模型"""

from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class QualityIssue(Base):
    __tablename__ = "quality_issue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_no = Column(String(64), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default='open')
    remark = Column(Text)

    # 提出信息
    submit_dept = Column(String(64))          # 提出部门
    submit_date = Column(Date)                # 提出日期
    submitter = Column(String(64))            # 提出人

    # 订单 & 产品
    order_no = Column(String(64), index=True) # 订单编号
    product_code = Column(String(64))         # 产品代码
    product_name = Column(String(128))        # 产品名称
    process = Column(String(64))              # 工序

    # 异常详情
    defect_type = Column(String(64))          # 缺陷类型
    root_cause = Column(Text)                 # 真实原因
    description = Column(Text)                # 异常描述

    # 责任
    responsible_person = Column(String(64))   # 责任人
    responsible_dept = Column(String(64))     # 责任部门

    # 数量
    batch_qty = Column(Integer)               # 批量数
    sample_qty = Column(Integer)              # 抽样数量
    defect_qty = Column(Integer)              # 不良数

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
