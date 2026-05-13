"""规则配置中心 — 责任归属配置模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class ResponsibilityMap(Base):
    __tablename__ = "responsibility_map"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_item_code = Column(String(64), nullable=False, comment="关联的点检规则 item_code")
    department = Column(String(64), nullable=False, comment="责任部门")
    role_name = Column(String(64), nullable=False, comment="责任人角色 (计划员/采购员)")
    user_id = Column(String(64), nullable=True, comment="具体用户ID (可选)")
    user_name = Column(String(64), nullable=True, comment="具体用户名 (可选)")
    escalation_level = Column(Integer, nullable=True, default=0, comment="升级层级 (0-不升级, 1-主管, 2-经理)")
    is_active = Column(Boolean, nullable=False, default=True, comment="启用状态")
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
