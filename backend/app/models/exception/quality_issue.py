"""异常与质量中心 — 品质异常模型"""

from sqlalchemy import text, Column, Integer, String, Date, DateTime, Text, Boolean
from sqlalchemy.sql import func

from app.core.database import Base


class QualityIssue(Base):
    __tablename__ = "quality_issue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    erp_quality_id = Column(String(64), unique=True, index=True)
    issue_no = Column(String(64), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default='open')
    workflow_status = Column(String(32), nullable=False, server_default=text("'创建'"), default='创建')  # 流程状态: 创建/提交/批准/归档
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

    # 改善对策
    improvement_countermeasures = Column(Text)  # 改善对策
    improvement_countermeasures_date = Column(Date)  # 改善对策日期

    # 临时对策
    temporary_countermeasure = Column(Text)  # 临时对策
    temporary_countermeasure_date = Column(Date)  # 临时对策时间

    # 分析
    preliminary_analysis = Column(Text)  # 初步分析
    preliminary_analysis_person = Column(String(64))  # 初步分析负责人
    root_cause_analysis_person = Column(String(64))  # 真因分析负责人

    # 审批
    audit_comment = Column(Text)  # 审核意见
    auditor = Column(String(64))  # 审核人
    quality_manager_approval = Column(Text)  # 品质经理审批
    general_manager_approval = Column(Text)  # 总经理审批
    missed_inspector = Column(String(64))  # 漏检人

    # 来源 & 软删除
    data_source = Column(String(32), default='manual', index=True)  # 数据来源: erp / manual / excel
    is_deleted = Column(Boolean, default=False, index=True)  # 软删除标记(源端已删除)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
