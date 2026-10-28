"""智能体会话与消息持久化（SQL 为事实来源，Redis 为热缓存）。"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class AgentConversation(Base):
    __tablename__ = "agent_conversation"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id = Column(BigInteger, ForeignKey("agent.id"), nullable=False)
    user_id = Column(Integer, nullable=False)
    task_id = Column(BigInteger, nullable=True)
    title = Column(String(200), nullable=True)
    status = Column(String(16), nullable=False, default="active", server_default="active", comment="active|archived")
    last_message_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_conversation_agent_last", "agent_id", "last_message_at"),
        Index("ix_agent_conversation_task", "task_id"),
    )


class AgentMessage(Base):
    __tablename__ = "agent_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(BigInteger, ForeignKey("agent_conversation.id"), nullable=False)
    role = Column(String(16), nullable=False, comment="user|assistant|tool|system")
    content = Column(Text, nullable=True)
    tool_calls = Column(JSONB, nullable=True, comment="裁剪后的工具调用摘要")
    tool_results = Column(JSONB, nullable=True, comment="裁剪后的工具结果摘要")
    token_usage = Column(JSONB, nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_message_conversation_id", "conversation_id", "id"),
    )
