"""MRP 域 — 替代料规则模型"""

from sqlalchemy import Boolean, Column, Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.sql import func

from app.core.database import Base


class MrpSubstitute(Base):
    __tablename__ = "mrp_substitute"
    __table_args__ = (
        UniqueConstraint("main_material_id", "substitute_material_id", name="uq_mrp_substitute_main_sub"),
        Index("ix_mrp_substitute_main", "main_material_id"),
        Index("ix_mrp_substitute_sub", "substitute_material_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    main_material_id = Column(Integer, nullable=False, comment="主料ID(erp_material_id)")
    substitute_material_id = Column(Integer, nullable=False, comment="替代料ID(erp_material_id)")
    priority = Column(Integer, nullable=False, default=1, server_default="1", comment="优先级(数值小者优先)")
    policy = Column(String(16), nullable=False, default="priority", server_default="priority", comment="priority 按优先级 / ratio 按比例")
    ratio = Column(Numeric(9, 4), nullable=True, comment="比例(policy=ratio 时用，同主料下合计 100)")
    substitute_mode = Column(String(16), nullable=False, default="offset", server_default="offset", comment="offset 消耗替代料余额顶缺口 / replace 缺口建议改落替代料")
    valid_from = Column(Date, nullable=True, comment="生效日期")
    valid_to = Column(Date, nullable=True, comment="失效日期")
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"), comment="启用")
    remark = Column(Text, nullable=True)
    data_source = Column(String(20), nullable=False, default="manual", server_default="manual", comment="manual/excel")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
