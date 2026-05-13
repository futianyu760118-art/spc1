"""通义千问 (DashScope) Provider — 需安装 dashscope 包并配置 API Key"""

import logging
from typing import List, Optional, Type

from pydantic import BaseModel

from app.services.ai.base import LLMProvider, ChatMessage, ChatOptions

logger = logging.getLogger(__name__)

try:
    import dashscope
    from dashscope import Generation
    _HAS_DASHSCOPE = True
except ImportError:
    _HAS_DASHSCOPE = False


class DashscopeProvider(LLMProvider):

    def __init__(self, api_key: str = "", model: str = "qwen-plus", timeout: int = 30):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

        if _HAS_DASHSCOPE and self._api_key:
            dashscope.api_key = self._api_key

    @property
    def name(self) -> str:
        return "dashscope"

    def is_available(self) -> bool:
        return _HAS_DASHSCOPE and bool(self._api_key)

    async def chat(self, messages: List[ChatMessage], options: Optional[ChatOptions] = None) -> str:
        if not self.is_available():
            raise RuntimeError("Dashscope provider is not available")

        import asyncio

        opts = options or ChatOptions()
        formatted = [{"role": m.role, "content": m.content} for m in messages]

        # dashscope SDK 是同步的，用 run_in_executor 包装
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: Generation.call(
                model=self._model,
                messages=formatted,
                temperature=opts.temperature,
                max_tokens=opts.max_tokens,
                result_format="message",
            ),
        )

        if response.status_code != 200:
            raise RuntimeError(f"Dashscope error: {response.code} - {response.message}")

        content = response.output.choices[0].message.content or ""
        logger.info(f"[Dashscope] model={self._model} tokens={response.usage.get('total_tokens', '?')}")
        return content
