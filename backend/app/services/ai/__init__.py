"""统一 AI 服务层"""

from app.services.ai.base import LLMProvider, ChatMessage, ChatOptions, NotSupportedError
from app.services.ai.service import ai_service, AIService

__all__ = ["ai_service", "AIService", "LLMProvider", "ChatMessage", "ChatOptions", "NotSupportedError"]
