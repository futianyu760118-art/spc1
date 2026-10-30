"""智能体团队勾选关系：用户 → 智能体成员，平铺无层级。"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class AgentTeamMember(Base):
    __tablename__ = "agent_team_member"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("sys_user.id"), nullable=False, comment="团队属主用户")
    agent_id = Column(BigInteger, ForeignKey("agent.id"), nullable=False, comment="勾选的智能体")
    created_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="uq_agent_team_member_user_agent"),
        Index("ix_agent_team_member_user_id", "user_id"),
    )
