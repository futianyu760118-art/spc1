"""OpenAI Provider — 需安装 openai 包并配置 API Key"""

import logging
from typing import List, Optional, Type

from pydantic import BaseModel

from app.services.ai.base import LLMProvider, ChatMessage, ChatOptions

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False


class OpenAIProvider(LLMProvider):

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini", base_url: str = "", timeout: int = 30):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url or None
        self._timeout = timeout
        self._client: Optional["AsyncOpenAI"] = None

        if _HAS_OPENAI and self._api_key:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        return _HAS_OPENAI and bool(self._api_key) and self._client is not None

    async def chat(self, messages: List[ChatMessage], options: Optional[ChatOptions] = None) -> str:
        if not self.is_available():
            raise RuntimeError("OpenAI provider is not available")

        opts = options or ChatOptions()
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=opts.temperature,
            max_tokens=opts.max_tokens,
        )
        content = response.choices[0].message.content or ""
        logger.info(f"[OpenAI] model={self._model} tokens={response.usage.total_tokens if response.usage else '?'}")
        return content
