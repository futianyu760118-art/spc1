"""网关派单审计：caller 路由与拒绝记录。"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, String, func

from app.core.database import Base


class GatewayDispatchLog(Base):
    __tablename__ = "gateway_dispatch_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(String(128), nullable=False)
    trace_id = Column(String(128), nullable=True)
    capability = Column(String(64), nullable=False)
    caller_system_id = Column(String(64), nullable=True)
    caller_agent_id = Column(String(64), nullable=True)
    caller_user_id = Column(String(64), nullable=True)
    caller_task_id = Column(String(64), nullable=True)
    caller_trace_id = Column(String(128), nullable=True)
    resolved_user_id = Column(Integer, nullable=True)
    mode = Column(String(16), nullable=False, comment="user|system")
    result = Column(String(16), nullable=False, comment="routed|rejected")
    reject_reason = Column(String(32), nullable=True)
    caller_user_mismatch = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_gateway_dispatch_log_run_id", "run_id"),
        Index("ix_gateway_dispatch_log_trace_id", "trace_id"),
        Index("ix_gateway_dispatch_log_caller_agent_id", "caller_agent_id"),
        Index("ix_gateway_dispatch_log_created_at", "created_at"),
    )
