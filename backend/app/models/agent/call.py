"""智能体调用记录：用户助手 → 智能体成员的一次能力调用。"""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class AgentCallLog(Base):
    __tablename__ = "agent_call_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trace_id = Column(String(128), nullable=False, index=True)
    caller_user_id = Column(Integer, nullable=False)
    callee_agent_id = Column(BigInteger, nullable=True, index=True)
    capability = Column(String(64), nullable=False)
    instruction_summary = Column(String(500), nullable=True)
    status = Column(String(16), nullable=False, default="running", server_default="running")
    result_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_call_log_caller_created", "caller_user_id", "created_at"),
        Index("ix_agent_call_log_callee_created", "callee_agent_id", "created_at"),
    )
