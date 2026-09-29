"""问题反馈 schemas"""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


class FeedbackAttachment(BaseModel):
    key: str
    url: str
    name: str
    size: int = 0
    mime: Optional[str] = None


class FeedbackCreate(BaseModel):
    type: str = "issue"  # issue/suggestion/inquiry
    severity: str = "low"  # low/medium/high
    page_path: Optional[str] = None
    title: str
    description: str
    attachments: Optional[List[FeedbackAttachment]] = None


class FeedbackUpdate(BaseModel):
    type: Optional[str] = None
    severity: Optional[str] = None
    page_path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    attachments: Optional[List[FeedbackAttachment]] = None


class FeedbackReply(BaseModel):
    reply: Optional[str] = None  # 可为空（仅改状态时）
    status: Optional[str] = None  # 可同时改状态


class FeedbackStatusUpdate(BaseModel):
    status: str  # pending/processing/resolved/closed


class FeedbackAiFinish(BaseModel):
    success: bool
    branch: Optional[str] = None
    summary: Optional[str] = None
    error: Optional[str] = None


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    severity: str
    page_path: Optional[str] = None
    title: str
    description: str
    attachments: Optional[List[Any]] = None
    status: str
    reply: Optional[str] = None
    replied_by: Optional[str] = None
    replied_at: Optional[datetime] = None
    submitter_id: int
    submitter_name: str
    created_at: Optional[datetime] = None
    ai_status: Optional[str] = "none"
    ai_branch: Optional[str] = None
    ai_note: Optional[str] = None
    ai_requested_by: Optional[str] = None
    ai_requested_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FeedbackListOut(BaseModel):
    items: List[FeedbackOut]
    total: int
    page: int
    page_size: int
    stats: Optional[dict] = None
