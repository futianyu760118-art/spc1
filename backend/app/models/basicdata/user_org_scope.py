"""基础数据与集成中心 — 用户组织数据范围模型"""

from sqlalchemy import Column, BigInteger, Integer, Boolean, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class UserOrgScope(Base):
    __tablename__ = "sys_user_org_scope"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, comment="用户ID，关联sys_user.id")
    org_id = Column(BigInteger, nullable=False, comment="组织ID，关联scm_organization.id")
    include_sub = Column(Boolean, nullable=False, default=True, comment="是否包含子组织")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_user_org_scope"),
    )