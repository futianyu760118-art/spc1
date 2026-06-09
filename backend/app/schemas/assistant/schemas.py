"""智能助手 — Schemas"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None


class AssistantCard(BaseModel):
    type: str  # "summary" | "order_list" | "text" | "search_result_list" | "action_list"
    title: str = ""
    payload: Any = None


class AssistantReply(BaseModel):
    intent: str = "unknown"
    text: str = ""
    cards: List[AssistantCard] = []
    suggestions: List[str] = []
    session_id: Optional[str] = None
    provider: str = "rule_based"
    trace_id: Optional[str] = None
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
