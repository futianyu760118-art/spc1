"""审批中心 - SQL 接入业务注册模型（管理员配置只读 SQL + 字段映射，零开发接入）。"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ApprovalBusiness(Base):
    __tablename__ = "approval_business"

    id = Column(Integer, primary_key=True, autoincrement=True)
    biz_type = Column(String(64), nullable=False, unique=True, comment="业务标识（全局唯一）")
    biz_name = Column(String(128), nullable=False, comment="业务名称")
    mode = Column(String(16), nullable=False, default="sql", comment="接入方式：sql（内置 provider 不入此表）")
    sql_text = Column(Text, nullable=False, comment="只读取数 SQL")
    field_mapping_json = Column(Text, nullable=False, default="{}", comment="字段映射 JSON：内部字段 -> 来源列")
    condition_fields_json = Column(Text, nullable=False, default="[]", comment="条件字段声明 [{value,label}]")
    deep_link_template = Column(String(256), nullable=True, comment="业务详情链接模板，如 /purchase/pay/{no}")
    description = Column(String(256), nullable=True, comment="业务说明")
    is_active = Column(Boolean, nullable=False, default=True, comment="停用后不再聚合与提醒")
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
