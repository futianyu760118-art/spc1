"""物料齐套中心 — 问题物料模型（对齐 3.1问题物料.csv）"""

from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean
from sqlalchemy.sql import func

from app.core.database import Base


class MaterialIssue(Base):
    __tablename__ = "material_issue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, index=True)
    week_no = Column(Integer, index=True)
    department = Column(String(64), index=True)
    category = Column(String(32))
    issue_date = Column(Date)
    reporter = Column(String(64))
    description = Column(Text)
    deadline = Column(Date)
    responsible_dept = Column(String(64))
    responsible_person = Column(String(64))
    audit_score = Column(Integer)
    is_project = Column(Boolean, default=False)
    follow_up_record = Column(Text)
    status = Column(String(32), nullable=False, default="open", index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
