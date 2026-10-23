"""基础数据与集成中心 — 智能体运行时配置与助手用量审计模型（管理台 2026-10 版）"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class AiAgentConfig(Base):
    """智能体运行时配置（scope='assistant' | 'execution_agent'），env 为兜底默认值"""

    __tablename__ = "ai_agent_config"
    __table_args__ = (
        UniqueConstraint("scope", "config_key", name="uq_ai_agent_config_scope_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(32), nullable=False, comment="assistant | execution_agent | execution_query | execution_reasoning | execution_order")
    config_key = Column(String(64), nullable=False, comment="配置键（白名单校验）")
    config_value = Column(Text, nullable=True, comment="配置值（空=回退代码默认）")
    value_type = Column(String(8), nullable=False, default="string", comment="string|int|float|bool|json")
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class AssistantRun(Base):
    """智能助手单次对话用量审计（chat 与 SSE 流式各落一条）"""

    __tablename__ = "assistant_run"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True, index=True)
    user_message = Column(String(500), nullable=True)
    intent = Column(String(32), nullable=True, comment="query_data|analyze_history|general_chat|agent|unknown")
    tools_called = Column(JSONB, nullable=True, comment="工具名数组（按调用序去重）")
    tool_rounds = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Numeric(12, 2), nullable=True)
    is_success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
