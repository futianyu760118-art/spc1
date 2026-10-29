"""智能体目录：管理员预创建、与员工隔离，每个条目具备一或多类能力。"""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class Agent(Base):
    """智能体目录条目：名称 + 能力列表 + 开放范围 + 启停。"""

    __tablename__ = "agent"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_no = Column(String(32), nullable=False, unique=True, comment="AG-xxxxxx 或 AG-SYS-XXX")
    display_name = Column(String(64), nullable=False, comment="智能体名称（全局唯一）")
    capability_codes = Column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"),
        comment="能力码列表（非空、去重），见 capabilities.CONFIGURABLE_CAPABILITIES",
    )
    scope_type = Column(String(16), nullable=False, default="all", server_default="all", comment="all|roles")
    scope_role_ids = Column(JSONB, nullable=True, comment="scope_type=roles 时的角色 id 列表")
    description = Column(String(500), nullable=True, comment="展示与 LLM 选成员说明")
    status = Column(String(16), nullable=False, default="active", server_default="active", comment="active|disabled")
    config_version = Column(Integer, nullable=False, default=1, server_default="1")
    created_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_status", "status"),
    )
