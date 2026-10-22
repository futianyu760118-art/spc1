"""单据完整性规则（AI 助手缺字段通知）。"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class CompletenessRule(Base):
    __tablename__ = "completeness_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    biz_type = Column(String(32), nullable=False, comment="业务类型，如 order")
    field_key = Column(String(64), nullable=False, comment="字段键，必须在 available_fields 内")
    label = Column(String(64), nullable=False, comment="字段显示名（通知文案用）")
    required = Column(Boolean, nullable=False, default=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("biz_type", "field_key", name="uq_completeness_rule_biz_field"),
    )
