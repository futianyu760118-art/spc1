"""基础数据与集成中心 — 用户/角色模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class SysRole(Base):
    __tablename__ = "sys_role"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_code = Column(String(32), nullable=False, unique=True)
    role_name = Column(String(64), nullable=False)
    permissions = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)



class SysUser(Base):
    __tablename__ = "sys_user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True)
    display_name = Column(String(128))
    hashed_password = Column(String(256), nullable=False)
    role_id = Column(Integer, nullable=False)
    emp_code = Column(String(20), nullable=True, comment="关联员工工号")
    is_active = Column(Boolean, nullable=False, default=True)
    login_version = Column(Integer, nullable=False, default=0, comment="登录版本号，用于单点登录控制")
    last_token_jti = Column(String(64), nullable=True, comment="上一次登录的token jti，用于立即失效")
    last_login_time = Column(DateTime, nullable=True, comment="最后一次登录时间")
    font_size_scale = Column(String(10), nullable=True, default='1.0', comment="字体大小缩放比例")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
