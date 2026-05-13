"""异常与质量中心 — 问题日志模型（对齐0.1问题日志.csv）"""

from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class IssueLog(Base):
    __tablename__ = "issue_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seq_no = Column(Integer)
    recorder = Column(String(64))
    record_date = Column(Date)
    description = Column(Text)
    impact = Column(Text)
    interaction = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
