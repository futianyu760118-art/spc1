"""规则配置中心 — 点检规则配置模型"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class InspectionRule(Base):
    __tablename__ = "inspection_rule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_code = Column(String(32), nullable=False, comment="所属模块 (order/material/assembly)")
    rule_type = Column(String(32), nullable=False, comment="规则类型 (预警规则/责任规则/节点标准)")
    item_code = Column(String(64), nullable=False, unique=True, comment="点检项编码")
    item_name = Column(String(128), nullable=False, comment="点检项名称")
    parent_code = Column(String(64), nullable=True, comment="父级编码，用于树状结构")
    standard_desc = Column(Text, nullable=True, comment="标准说明")
    sort_order = Column(Integer, nullable=True, default=0, comment="排序号")
    is_active = Column(Boolean, nullable=False, default=True, comment="启用状态")
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
