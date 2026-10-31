"""规则版 Provider — 关键词匹配兜底，无外部依赖"""

from typing import List, Optional, Type

from pydantic import BaseModel

from app.services.ai.base import LLMProvider, ChatMessage, ChatOptions, NotSupportedError


class RuleBasedProvider(LLMProvider):
    """永远可用的关键词规则引擎，不调用任何外部 API"""

    @property
    def name(self) -> str:
        return "rule_based"

    def is_available(self) -> bool:
        return True

    async def chat(self, messages: List[ChatMessage], options: Optional[ChatOptions] = None) -> str:
        """简单关键词匹配回复（仅用于 assistant intent 解析场景兜底）"""
        if not messages:
            return "您好，请问有什么可以帮助您的？"

        last_msg = messages[-1].content if messages else ""
        # 规则引擎不做复杂对话，返回通用回复
        return f"[rule_based] 收到消息: {last_msg}"

    async def structured_output(
        self,
        prompt: str,
        schema: Type[BaseModel],
        options: Optional[ChatOptions] = None,
    ) -> BaseModel:
        """规则版不支持结构化输出，由上层退化为关键词路径"""
        raise NotSupportedError("RuleBasedProvider 不支持 structured_output，请使用关键词解析路径")
