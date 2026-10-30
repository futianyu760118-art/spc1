"""问题反馈 schemas"""
from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict


class FeedbackAttachment(BaseModel):
    key: str
    url: str
    name: str
    size: int = 0
    mime: Optional[str] = None


FeedbackType = Literal["issue", "suggestion", "inquiry"]
FeedbackSeverity = Literal["low", "medium", "high"]


class FeedbackCreate(BaseModel):
    type: FeedbackType = "issue"
    severity: FeedbackSeverity = "low"
    page_path: Optional[str] = None
    title: str
    description: str
    attachments: Optional[List[FeedbackAttachment]] = None


class FeedbackUpdate(BaseModel):
    type: Optional[FeedbackType] = None
    severity: Optional[FeedbackSeverity] = None
    page_path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    attachments: Optional[List[FeedbackAttachment]] = None


class FeedbackReply(BaseModel):
    reply: Optional[str] = None  # 可为空（仅改状态时）
    status: Optional[str] = None  # 可同时改状态


class FeedbackStatusUpdate(BaseModel):
    status: str  # pending/processing/resolved/closed


class FeedbackAiResultFile(BaseModel):
    path: str
    status: str = "M"  # A/M/D
    additions: int = 0
    deletions: int = 0


class FeedbackAiResultGate(BaseModel):
    name: str  # backend/frontend
    passed: bool
    exitCode: Optional[int] = None
    durationSeconds: Optional[int] = None
    outputTail: Optional[str] = None


class FeedbackAiResult(BaseModel):
    branch: Optional[str] = None
    summary: Optional[str] = None
    files: Optional[List[FeedbackAiResultFile]] = None
    gates: Optional[List[FeedbackAiResultGate]] = None
    runDir: Optional[str] = None
    error: Optional[str] = None


class FeedbackAiFinish(BaseModel):
    success: bool
    branch: Optional[str] = None
    summary: Optional[str] = None
    error: Optional[str] = None
    result: Optional[FeedbackAiResult] = None


class FeedbackAiProgress(BaseModel):
    stage: Optional[str] = None          # 阶段 key，白名单校验
    actions: Optional[List[str]] = None  # 动作批，单次最多 20 条


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
    ai_stage: Optional[str] = None
    ai_stage_started_at: Optional[datetime] = None
    ai_progress: Optional[List[Any]] = None
    ai_result: Optional[dict] = None
    updated_at: Optional[datetime] = None


class FeedbackListOut(BaseModel):
    items: List[FeedbackOut]
    total: int
    page: int
    page_size: int
    stats: Optional[dict] = None
