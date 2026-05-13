"""智能助手服务层"""

from app.services.assistant.intent_parser import parse_intent
from app.services.assistant.intent_router import dispatch

__all__ = ["parse_intent", "dispatch"]
