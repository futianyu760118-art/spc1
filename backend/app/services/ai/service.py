"""AIService — 统一入口，按配置选择 provider，失败时 fallback 到 rule_based"""

import logging
from typing import AsyncIterator, List, Optional, Type

from pydantic import BaseModel

from app.core.config import get_settings
from app.services.ai.base import LLMProvider, ChatMessage, ChatOptions, ChatWithToolsResult, NotSupportedError
from app.services.ai.rule_based import RuleBasedProvider
from app.services.ai.openai_provider import OpenAIProvider
from app.services.ai.dashscope_provider import DashscopeProvider

logger = logging.getLogger(__name__)


class AIService:
    """统一 AI 服务单例，对外暴露 chat / structured_output"""

    def __init__(self):
        settings = get_settings()
        self._rule_based = RuleBasedProvider()
        self._providers: dict[str, LLMProvider] = {
            "rule_based": self._rule_based,
        }

        # 注册 OpenAI
        openai_provider = OpenAIProvider(
            api_key=settings.AI_OPENAI_API_KEY,
            model=settings.AI_OPENAI_MODEL,
            base_url=settings.AI_OPENAI_BASE_URL,
            timeout=settings.AI_REQUEST_TIMEOUT,
        )
        logger.info(f"OpenAI Provider 初始化: api_key={'***' if settings.AI_OPENAI_API_KEY else 'EMPTY'}, base_url={settings.AI_OPENAI_BASE_URL}, model={settings.AI_OPENAI_MODEL}")
        if openai_provider.is_available():
            self._providers["openai"] = openai_provider
            logger.info("OpenAI Provider 注册成功")
        else:
            logger.warning("OpenAI Provider 不可用，跳过注册")

        # 注册 Dashscope
        dashscope_provider = DashscopeProvider(
            api_key=settings.AI_DASHSCOPE_API_KEY,
            model=settings.AI_DASHSCOPE_MODEL,
            timeout=settings.AI_REQUEST_TIMEOUT,
        )
        if dashscope_provider.is_available():
            self._providers["dashscope"] = dashscope_provider

        # 选择默认 provider
        default_name = settings.AI_DEFAULT_PROVIDER
        logger.info(f"配置的默认 provider: {default_name}")
        logger.info(f"可用的 providers: {list(self._providers.keys())}")
        if default_name in self._providers:
            self._default = self._providers[default_name]
            logger.info(f"使用默认 provider: {default_name}")
        else:
            logger.warning(f"配置的默认 provider '{default_name}' 不可用，fallback 到 rule_based")
            self._default = self._rule_based

        logger.info(f"AIService 初始化完成, 当前 provider={self._default.name}, 可用={list(self._providers.keys())}")

    def current_provider(self) -> str:
        return self._default.name

    def get_provider(self, name: Optional[str] = None) -> LLMProvider:
        if name and name in self._providers:
            return self._providers[name]
        return self._default

    async def chat(
        self,
        messages: List[ChatMessage],
        options: Optional[ChatOptions] = None,
        provider_name: Optional[str] = None,
    ) -> str:
        provider = self.get_provider(provider_name)
        try:
            return await provider.chat(messages, options)
        except Exception as e:
            if provider.name != "rule_based":
                logger.error(f"[{provider.name}] chat 失败: {e}, fallback 到 rule_based")
                return await self._rule_based.chat(messages, options)
            raise

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        options: Optional[ChatOptions] = None,
        provider_name: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """流式对话，逐 token 返回文本"""
        provider = self.get_provider(provider_name)
        try:
            async for chunk in provider.chat_stream(messages, options):
                yield chunk
        except Exception as e:
            if provider.name != "rule_based":
                logger.error(f"[{provider.name}] chat_stream 失败: {e}, fallback 到非流式")
                result = await self._rule_based.chat(messages, options)
                yield result
            else:
                raise

    async def chat_with_tools(
        self,
        messages: List[ChatMessage],
        tools: List[dict],
        options: Optional[ChatOptions] = None,
        provider_name: Optional[str] = None,
    ) -> ChatWithToolsResult:
        """带工具定义的对话，支持 function calling"""
        provider = self.get_provider(provider_name)
        try:
            return await provider.chat_with_tools(messages, tools, options)
        except NotSupportedError:
            raise
        except Exception as e:
            logger.error(f"[{provider.name}] chat_with_tools 失败: {e}")
            raise

    async def structured_output(
        self,
        prompt: str,
        schema: Type[BaseModel],
        options: Optional[ChatOptions] = None,
        provider_name: Optional[str] = None,
    ) -> BaseModel:
        """结构化输出，若 provider 不支持则抛 NotSupportedError"""
        provider = self.get_provider(provider_name)
        return await provider.structured_output(prompt, schema, options)


# 全局单例
ai_service = AIService()
