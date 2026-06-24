"""权限定义模型"""

from sqlalchemy import BigInteger, Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class SysPermission(Base):
    __tablename__ = "sys_permission"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(128), nullable=False, unique=True, comment="权限标识，如 production.schedule_plans")
    name = Column(String(128), nullable=False, comment="权限名称，如 计划排产")
    module = Column(String(64), nullable=False, comment="顶级模块 code，如 production")
    parent_code = Column(String(128), nullable=True, comment="父级权限 code，如 production")
    actions = Column(JSONB, nullable=False, default=lambda: ["create", "read", "update", "delete"], comment="该权限支持的操作列表")
    route_path = Column(String(128), nullable=True, comment="前端路由路径，如 /schedule-plans")
    sort_order = Column(Integer, nullable=False, default=0, comment="同级排序")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否启用")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
