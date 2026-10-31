"""问题反馈模型"""
from sqlalchemy import text, Column, Integer, String, Text, DateTime
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

    # AI 自动实现
    ai_status = Column(String(16), nullable=False, default="none", server_default=text("'none'"), index=True,
                       comment="none/queued/running/done/failed")
    ai_branch = Column(String(128), nullable=True, comment="runner 产出的本地分支名")
    ai_note = Column(Text, nullable=True, comment="runner 结果摘要/失败原因")
    ai_requested_by = Column(String(64), nullable=True, comment="派单人 username")
    ai_requested_at = Column(DateTime, nullable=True, comment="派单时间")
    ai_stage = Column(String(32), nullable=True,
                      comment="当前阶段（preparing/fetching/agent/gate_backend/gate_frontend/committing）")
    ai_stage_started_at = Column(DateTime, nullable=True, comment="当前阶段开始时间")
    ai_progress = Column(JSONB, nullable=True, comment="执行记录 [{at,kind,stage,text}]，保留最近 50 条")
    ai_result = Column(JSONB, nullable=True,
                       comment="结构化实现结果 {branch,summary,files,gates,runDir,error}，重排时清空")

    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
