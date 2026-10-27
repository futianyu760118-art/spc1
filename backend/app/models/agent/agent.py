"""智能体身份、层级与配置变更审计。"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class Agent(Base):
    __tablename__ = "agent"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_no = Column(String(32), nullable=False, unique=True, comment="AG-000001")
    user_id = Column(Integer, ForeignKey("sys_user.id"), nullable=False, unique=True, comment="绑定用户，一人一个")
    display_name = Column(String(64), nullable=True)
    parent_agent_id = Column(BigInteger, ForeignKey("agent.id"), nullable=True, comment="直属上级智能体")
    status = Column(String(16), nullable=False, default="active", server_default="active", comment="active|disabled")
    capability_policy = Column(JSONB, nullable=True, comment="granted/disabled/data_scope")
    config_version = Column(Integer, nullable=False, default=1, server_default="1")
    created_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_parent_agent_id", "parent_agent_id"),
        Index("ix_agent_status", "status"),
    )


class AgentConfigLog(Base):
    __tablename__ = "agent_config_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id = Column(BigInteger, ForeignKey("agent.id"), nullable=False, index=True)
    changed_by_user_id = Column(Integer, nullable=False)
    old_policy = Column(JSONB, nullable=True)
    new_policy = Column(JSONB, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class AgentHierarchyLog(Base):
    __tablename__ = "agent_hierarchy_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id = Column(BigInteger, ForeignKey("agent.id"), nullable=False, index=True)
    old_parent_id = Column(BigInteger, nullable=True)
    new_parent_id = Column(BigInteger, nullable=True)
    action = Column(String(16), nullable=False, comment="bind|reparent|unbind|lock|unlock")
    actor_user_id = Column(Integer, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
