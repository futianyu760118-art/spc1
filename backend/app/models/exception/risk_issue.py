"""异常与质量中心 — 风险问题模型"""

from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class RiskIssue(Base):
    __tablename__ = "risk_issue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_no = Column(String(64), nullable=False, unique=True)
    issue_type = Column(String(32), nullable=False)
    risk_level = Column(String(16), nullable=False)
    order_no = Column(String(64), index=True)
    line_no = Column(String(32))
    material_code = Column(String(64))
    po_no = Column(String(64))
    description = Column(Text)
    owner = Column(String(64))
    action_taken = Column(Text)
    commit_date = Column(Date)
    status = Column(String(32), nullable=False)
    closed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
