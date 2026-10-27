"""智能体任务账本：任务、事件流与汇报版本。"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class AgentTask(Base):
    __tablename__ = "agent_task"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_no = Column(String(32), nullable=False, unique=True, comment="AT-000001")
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(16), nullable=False, comment="business|general")
    biz_type = Column(String(32), nullable=True, comment="order|material_shortage|quality_issue")
    biz_id = Column(String(64), nullable=True)
    biz_no = Column(String(64), nullable=True)
    biz_context = Column(JSONB, nullable=True)
    biz_title = Column(String(256), nullable=True)
    biz_url = Column(String(512), nullable=True)
    assigner_agent_id = Column(BigInteger, ForeignKey("agent.id"), nullable=False)
    assigner_user_id = Column(Integer, nullable=False)
    assignee_agent_id = Column(BigInteger, ForeignKey("agent.id"), nullable=False)
    assignee_user_id = Column(Integer, nullable=False)
    priority = Column(String(8), nullable=False, default="normal", server_default="normal")
    status = Column(String(16), nullable=False, default="pending", server_default="pending")
    source = Column(String(16), nullable=False, default="supervisor_chat", server_default="supervisor_chat")
    due_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    analysis_status = Column(String(16), nullable=False, default="pending", server_default="pending")
    analysis_result = Column(JSONB, nullable=True)
    analysis_error = Column(Text, nullable=True)
    analysis_started_at = Column(DateTime, nullable=True)
    analysis_finished_at = Column(DateTime, nullable=True)
    analysis_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    latest_report_id = Column(BigInteger, nullable=True)
    reopen_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_task_assignee_status_due", "assignee_user_id", "status", "due_at"),
        Index("ix_agent_task_assigner_status_due", "assigner_user_id", "status", "due_at"),
        Index("ix_agent_task_status_analysis", "status", "analysis_status"),
        Index("ix_agent_task_biz", "biz_type", "biz_id"),
    )


class AgentTaskEvent(Base):
    __tablename__ = "agent_task_event"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("agent_task.id"), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)
    actor_agent_id = Column(BigInteger, nullable=True)
    actor_user_id = Column(Integer, nullable=True)
    from_status = Column(String(16), nullable=True)
    to_status = Column(String(16), nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class AgentTaskReport(Base):
    __tablename__ = "agent_task_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("agent_task.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    summary = Column(Text, nullable=False)
    result_data = Column(JSONB, nullable=True)
    evidence = Column(JSONB, nullable=True)
    submitted_by_agent_id = Column(BigInteger, nullable=False)
    submitted_by_user_id = Column(Integer, nullable=False)
    submitted_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("task_id", "version", name="uq_agent_task_report_version"),
    )
