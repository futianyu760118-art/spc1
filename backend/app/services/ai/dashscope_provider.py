"""通义千问 (DashScope) Provider — 需安装 dashscope 包并配置 API Key"""

import logging
from typing import AsyncIterator, List, Optional, Type

from pydantic import BaseModel

from app.services.ai.base import LLMProvider, ChatMessage, ChatOptions, ChatWithToolsResult, ToolCall, TokenUsage

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
                model=(opts.model if opts and opts.model else self._model),
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

    async def chat_stream(self, messages: List[ChatMessage], options: Optional[ChatOptions] = None) -> AsyncIterator[str]:
        """流式对话，逐 chunk 返回文本"""
        if not self.is_available():
            raise RuntimeError("Dashscope provider is not available")

        import asyncio

        opts = options or ChatOptions()
        formatted = [{"role": m.role, "content": m.content} for m in messages]

        loop = asyncio.get_event_loop()
        # DashScope 流式调用使用 stream=True 参数
        responses = await loop.run_in_executor(
            None,
            lambda: Generation.call(
                model=(opts.model if opts and opts.model else self._model),
                messages=formatted,
                temperature=opts.temperature,
                max_tokens=opts.max_tokens,
                result_format="message",
                stream=True,
                incremental_output=True,
            ),
        )

        for response in responses:
            if response.status_code != 200:
                raise RuntimeError(f"Dashscope stream error: {response.code} - {response.message}")
            content = response.output.choices[0].message.content
            if content:
                yield content

    async def chat_with_tools(
        self,
        messages: List[ChatMessage],
        tools: List[dict],
        options: Optional[ChatOptions] = None,
    ) -> ChatWithToolsResult:
        if not self.is_available():
            raise RuntimeError("Dashscope provider is not available")

        import asyncio
        import json as _json

        opts = options or ChatOptions()
        formatted = []
        for m in messages:
            msg: dict = {"role": m.role, "content": m.content}
            if hasattr(m, "tool_call_id") and m.role == "tool":
                msg["tool_call_id"] = m.tool_call_id  # type: ignore
            if hasattr(m, "tool_calls") and m.role == "assistant" and getattr(m, "tool_calls", None):
                msg["tool_calls"] = m.tool_calls  # type: ignore
                if not m.content:
                    msg.pop("content", None)
            formatted.append(msg)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: Generation.call(
                model=(opts.model if opts and opts.model else self._model),
                messages=formatted,
                tools=tools if tools else None,
                temperature=opts.temperature,
                max_tokens=opts.max_tokens,
                result_format="message",
            ),
        )

        if response.status_code != 200:
            raise RuntimeError(f"Dashscope error: {response.code} - {response.message}")

        choice_msg = response.output.choices[0].message
        usage = response.usage or {}
        logger.info(f"[Dashscope tools] model={self._model} tokens={usage.get('total_tokens', '?')}")

        result = ChatWithToolsResult()
        if hasattr(choice_msg, 'content') and choice_msg.content:
            result.text = choice_msg.content
        if hasattr(choice_msg, 'tool_calls') and choice_msg.tool_calls:
            for tc in choice_msg.tool_calls:
                func_info = tc.get('function', tc) if isinstance(tc, dict) else tc.function
                if isinstance(func_info, dict):
                    fn_name = func_info.get('name', '')
                    fn_args_raw = func_info.get('arguments', '{}')
                else:
                    fn_name = func_info.name
                    fn_args_raw = func_info.arguments
                try:
                    args = _json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                except _json.JSONDecodeError:
                    args = {}
                tc_id = tc.get('id', '') if isinstance(tc, dict) else getattr(tc, 'id', '')
                result.tool_calls.append(ToolCall(id=tc_id or f"call_{fn_name}", name=fn_name, arguments=args))
        if isinstance(usage, dict) and usage:
            result.usage = TokenUsage(
                prompt_tokens=int(usage.get("input_tokens", 0) or 0),
                completion_tokens=int(usage.get("output_tokens", 0) or 0),
                total_tokens=int(usage.get("total_tokens", 0) or 0),
            )
        return result
