"""审批中心 - 审批域核心三表（实例 / 任务 / 流水）。

设计：docs/superpowers/specs/2026-09-29-approval-center-redesign-design.md
- approval_instance：一张单据一条（unique biz_type+biz_id），审批状态唯一权威；
  rejected/recalled 可重新提交（复用同一行重置为 pending，流水按 submit 分轮）。
- approval_task：节点激活时按快照展开到人（或签：任一人审批即通过，同级其余置 skipped）；
  待办 = approver=me AND status='active'。
- approval_record：全操作流水（与旧每业务日志表同构，统一 instance_id 关联）。
"""

from sqlalchemy import (Column, DateTime, Float, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.sql import func

from app.core.database import Base


class ApprovalInstance(Base):
    __tablename__ = "approval_instance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    biz_type = Column(String(64), nullable=False, comment="业务标识")
    biz_id = Column(Integer, nullable=False, comment="业务单据数字主键")
    biz_no = Column(String(128), comment="单号（展示用）")
    title = Column(String(256), comment="标题")
    summary = Column(Text, comment="摘要")
    applicant = Column(String(64), nullable=False, comment="申请人 username")
    amount = Column(Float, comment="金额（条件路由/展示）")
    extra_json = Column(Text, nullable=False, default="{}", comment="条件字段值快照 JSON")
    status = Column(String(16), nullable=False, default="pending",
                    comment="pending|approved|rejected|recalled")
    current_level = Column(Integer, nullable=False, default=1)
    snapshot_json = Column(Text, nullable=False, default="[]", comment="节点快照（与旧引擎格式一致）")
    timeout_hours = Column(Integer, comment="当前节点超时小时数（0=不提醒，NULL=未配置）")
    version = Column(Integer, nullable=False, default=1, comment="乐观锁")
    submitted_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("biz_type", "biz_id", name="uq_approval_instance_biz"),
        Index("ix_approval_instance_status", "status"),
        Index("ix_approval_instance_applicant", "applicant"),
    )


class ApprovalTask(Base):
    __tablename__ = "approval_task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(Integer, nullable=False)
    node_seq = Column(Integer, nullable=False)
    node_label = Column(String(128), nullable=False)
    role_code = Column(String(64), comment="节点角色（快照）")
    approver = Column(String(64), nullable=False, comment="审批人 username")
    status = Column(String(16), nullable=False, default="active",
                    comment="active|approved|rejected|skipped|canceled")
    comment = Column(Text)
    acted_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_approval_task_approver", "approver", "status"),
        Index("ix_approval_task_instance", "instance_id"),
    )


class ApprovalRecord(Base):
    __tablename__ = "approval_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(Integer, nullable=False)
    action = Column(String(16), nullable=False, comment="submit|approve|reject|recall|auto_skip|revoked")
    node_seq = Column(Integer)
    operator = Column(String(64), nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_approval_record_instance", "instance_id"),
    )
