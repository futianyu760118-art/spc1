"""规则配置中心 — 风险规则模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class RiskRule(Base):
    __tablename__ = "risk_rule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_code = Column(String(64), nullable=False, unique=True)
    rule_name = Column(String(128), nullable=False)
    rule_type = Column(String(32), nullable=False)
    condition_json = Column(JSONB)
    risk_level = Column(String(16), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(String(64))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
