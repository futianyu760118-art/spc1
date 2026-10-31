"""规则配置中心 — 节点标准配置模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class NodeStandard(Base):
    __tablename__ = "node_standard"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_code = Column(String(64), nullable=False, unique=True, comment="节点编码")
    node_name = Column(String(128), nullable=False, comment="节点名称 (备料周期/SMT贴片/组装生产)")
    time_value = Column(Integer, nullable=False, comment="标准值")
    time_unit = Column(String(16), nullable=False, default="天", comment="单位 (天/小时)")
    applicable_scene = Column(String(64), nullable=False, comment="适用场景 (内销/外销/标准品/新品)")
    description = Column(String(256), nullable=True, comment="描述")
    is_active = Column(Boolean, nullable=False, default=True, comment="启用状态")
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
