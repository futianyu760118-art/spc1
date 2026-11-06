"""下周排产计划：快照与推送收件人配置。"""

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class WeeklyPushRecipient(Base):
    __tablename__ = "weekly_push_recipient"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, unique=True)
    category = Column(String(64), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    remark = Column(Text, nullable=True)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class WeeklyPlanSnapshot(Base):
    __tablename__ = "weekly_plan_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_no = Column(String(64), nullable=False, unique=True, index=True)
    week_start = Column(Date, nullable=False, index=True)
    week_end = Column(Date, nullable=False)
    schedule_month = Column(String(7), nullable=True)
    batch_no = Column(String(64), nullable=True)
    summary_json = Column(JSONB, nullable=False, default=dict)
    detail_json = Column(JSONB, nullable=False, default=dict)
    status = Column(String(16), nullable=False, default="draft", index=True)
    generated_by = Column(String(64), nullable=True)
    generated_at = Column(DateTime, server_default=func.now(), nullable=False)
    published_at = Column(DateTime, nullable=True)
    share_link_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
