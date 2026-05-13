"""主数据与集成中心 — 同步SQL配置模型"""

from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class SyncSqlConfig(Base):
    __tablename__ = "sync_sql_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(String(32), nullable=False, unique=True)
    description = Column(String(256))
    sql_text = Column(Text, nullable=False)
    field_mapping_json = Column(Text)
    condition_params_json = Column(Text)
    
    # 同步配置字段
    sync_interval = Column(String(20), nullable=False, default="1h", comment="同步间隔 (1h/2h/6h/12h/1d/1w)")
    sync_strategy = Column(String(20), nullable=False, default="incremental", comment="同步策略 (incremental/full/hybrid)")
    sync_time_window = Column(String(50), nullable=True, comment="同步时间窗口 (如: 02:00-04:00 或 null表示不限)")
    sync_priority = Column(Integer, nullable=False, default=5, comment="同步优先级 (1-10, 数字越小优先级越高)")
    sync_enabled = Column(Boolean, default=True, comment="是否启用同步")
    
    # 同步时间跟踪
    last_sync_time = Column(DateTime, nullable=True, comment="上次同步时间")
    next_sync_time = Column(DateTime, nullable=True, comment="下次计划同步时间")
    last_sync_status = Column(String(20), nullable=True, comment="上次同步状态 (success/failed/running)")
    last_sync_message = Column(Text, nullable=True, comment="上次同步消息")
    
    # 兼容旧字段
    is_active = Column(Boolean, default=True)
    created_by = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
