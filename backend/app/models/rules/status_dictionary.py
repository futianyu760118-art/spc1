"""规则配置中心 — 状态字典配置模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class StatusDictionary(Base):
    __tablename__ = "status_dictionary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status_type = Column(String(64), nullable=False, comment="状态类型 (order_status/risk_level/po_status)")
    code = Column(String(32), nullable=False, comment="状态代码 (on_time/delayed/red/yellow)")
    name = Column(String(64), nullable=False, comment="状态名称 (正常/延迟/高风险)")
    color_tag = Column(String(32), nullable=False, comment="颜色标签 (red/yellow/green/white)")
    display_color = Column(String(16), nullable=True, comment="显示颜色值 (#FF0000)")
    sort_order = Column(Integer, nullable=True, default=0, comment="排序号")
    is_active = Column(Boolean, nullable=False, default=True, comment="启用状态")
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
