"""问题反馈模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(16), nullable=False, default="issue", index=True,
                  comment="issue/suggestion/inquiry")
    severity = Column(String(16), nullable=False, default="low", index=True,
                      comment="low/medium/high")
    page_path = Column(String(256), nullable=True, comment="所在页面 location.pathname")
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    attachments = Column(JSONB, nullable=True, comment="StoredFile 数组 [{key,url,name,size,mime}]")
    status = Column(String(16), nullable=False, default="pending", index=True,
                    comment="pending/processing/resolved/closed")

    # 管理员回复
    reply = Column(Text, nullable=True)
    replied_by = Column(String(64), nullable=True)
    replied_at = Column(DateTime, nullable=True)

    # 提交人
    submitter_id = Column(Integer, nullable=False, index=True)
    submitter_name = Column(String(64), nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
