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


class RoutingInfo(BaseModel):
    decision: str = "none"  # local | hub | none
    capability: Optional[str] = None
    agent_key: Optional[str] = None
    agent_label: Optional[str] = None
    reason: str = ""
    executed: bool = False
    dispatch_error: Optional[str] = None


class AssistantReply(BaseModel):
    intent: str = "unknown"
    text: str = ""
    thinking: Optional[str] = None
    cards: List[AssistantCard] = []
    suggestions: List[str] = []
    session_id: Optional[str] = None
    provider: str = "rule_based"
    trace_id: Optional[str] = None
    routing: Optional[RoutingInfo] = None
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
