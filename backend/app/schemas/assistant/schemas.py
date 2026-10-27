"""智能助手 — Schemas"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    conversation_id: Optional[int] = None
    task_id: Optional[int] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None


class AssistantCard(BaseModel):
    type: str  # "summary" | "order_list" | "text" | "search_result_list" | "action_list"
    title: str = ""
    payload: Any = None


class OrchestrationStep(BaseModel):
    """编排步骤（步骤时间线 / 审计）"""
    step_id: int
    tool: str  # call_query_agent | call_reasoning_agent | call_order_agent
    agent_label: str = ""
    capability: str = ""
    path: Optional[str] = None
    task_type: Optional[str] = None
    order_no: Optional[str] = None
    status: str = "running"  # running | completed | failed | blocked | pending_confirmation
    summary: str = ""
    error: Optional[str] = None
    item_count: Optional[int] = None
    duration_ms: Optional[float] = None


class WriteConfirmationField(BaseModel):
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class WriteConfirmationInfo(BaseModel):
    """写操作确认单（前端确认卡片；订单写与任务动作共用）"""
    confirmation_id: str
    action_type: str = "order_update"
    order_no: Optional[str] = None
    fields: List[WriteConfirmationField] = []
    preview: Optional[Dict[str, Any]] = None
    created_at: str = ""
    expires_at: str = ""
    status: str = "pending"  # pending | confirmed | cancelled | executed | failed
    write_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AssistantReply(BaseModel):
    intent: str = "unknown"
    text: str = ""
    thinking: Optional[str] = None
    cards: List[AssistantCard] = []
    suggestions: List[str] = []
    session_id: Optional[str] = None
    conversation_id: Optional[int] = None
    provider: str = "rule_based"
    trace_id: Optional[str] = None
    steps: List[OrchestrationStep] = []
    confirmation: Optional[WriteConfirmationInfo] = None
    diagnostics: Optional[Dict[str, Any]] = None


class SkillItem(BaseModel):
    intent: str
    name: str
    description: str
    keywords: List[str] = []
    category: Optional[str] = None


class ToolInfo(BaseModel):
    name: str
    description: str
