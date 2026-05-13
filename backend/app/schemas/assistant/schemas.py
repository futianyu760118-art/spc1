"""智能助手 — Schemas"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    message: str
    session_id: Optional[str] = None


class AssistantCard(BaseModel):
    type: str  # "order_list" | "summary" | "text"
    title: str = ""
    payload: Any = None


class AssistantReply(BaseModel):
    intent: str = "unknown"
    text: str = ""
    cards: List[AssistantCard] = []
    suggestions: List[str] = []
    session_id: Optional[str] = None
    provider: str = "rule_based"


class SkillItem(BaseModel):
    intent: str
    name: str
    description: str
    keywords: List[str] = []
