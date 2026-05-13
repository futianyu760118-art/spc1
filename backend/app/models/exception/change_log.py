"""异常与质量中心 — 变更日志模型（对齐0.1.1变更日志.csv）"""

from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ChangeLog(Base):
    __tablename__ = "change_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seq_no = Column(Integer)
    modifier = Column(String(64))
    change_date = Column(Date)
    change_content = Column(Text)
    impact = Column(Text)
    interaction = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
