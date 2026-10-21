"""OpenAI Provider — 需安装 openai 包并配置 API Key"""

import asyncio
import logging
from typing import AsyncIterator, List, Optional, Type

from pydantic import BaseModel

from app.services.ai.base import LLMProvider, ChatMessage, ChatOptions, ChatWithToolsResult, ToolCall, TokenUsage

logger = logging.getLogger(__name__)


def _unexpected_response_error(response) -> RuntimeError:
    # 部分 OpenAI 兼容网关（如 bigmodel.cn）在令牌失效/配额不足时返回 HTTP 200 + 错误 JSON，
    # SDK 解析后 choices 为 None，这里还原原始错误体避免 'NoneType' is not subscriptable
    extra = getattr(response, "model_extra", None) or {}
    detail = extra.get("msg") or extra.get("error") or str(extra) if extra else str(response)
    return RuntimeError(f"上游返回异常响应（choices 为空，常见于令牌失效/配额不足）: {detail}")


def _message_payload(message: ChatMessage) -> dict:
    """ChatMessage → OpenAI 请求体；保留工具调用链与 DeepSeek reasoning_content。"""
    payload: dict = {"role": message.role, "content": message.content}
    if message.role == "tool":
        payload["tool_call_id"] = message.tool_call_id
        return payload
    if message.role == "assistant" and message.tool_calls:
        payload["tool_calls"] = message.tool_calls
        if not (message.content or "").strip():
            payload.pop("content", None)
        if message.reasoning_content:
            payload["reasoning_content"] = message.reasoning_content
    return payload


def _reasoning_content(message) -> Optional[str]:
    extra = getattr(message, "model_extra", None) or {}
    return getattr(message, "reasoning_content", None) or extra.get("reasoning_content")


def _usage_dict(usage) -> dict:
    """openai SDK usage → {prompt/completion/total/cached}_tokens。

    缓存命中兼容两种口径：OpenAI 的 prompt_tokens_details.cached_tokens 与
    DeepSeek 的 prompt_cache_hit_tokens（SDK 未知字段落在 model_extra）。
    """
    if usage is None:
        return {}
    details = getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0)
    extra = getattr(usage, "model_extra", None) or {}
    if extra.get("prompt_cache_hit_tokens") is not None:
        cached = int(extra["prompt_cache_hit_tokens"] or 0)
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        "cached_tokens": cached,
    }

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

        if _HAS_OPENAI and (self._api_key or self._base_url):
            # 对于本地服务，API Key 可以为空，使用默认值
            api_key = self._api_key or "no-key-required"
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        # 对于本地模型服务，放宽检查条件
        if not _HAS_OPENAI:
            return False
        # API Key 可以为空（本地服务通常不需要）
        # 只要 base_url 配置了就认为可用
        return bool(self._base_url) or bool(self._api_key)

    async def chat(self, messages: List[ChatMessage], options: Optional[ChatOptions] = None) -> str:
        if not self.is_available():
            raise RuntimeError("OpenAI provider is not available")

        opts = options or ChatOptions()
        request_timeout = opts.timeout or self._timeout
        response = await asyncio.wait_for(
            self._client.chat.completions.create(
                model=opts.model or self._model,
                messages=[_message_payload(m) for m in messages],
                temperature=opts.temperature,
                max_tokens=opts.max_tokens,
            ),
            timeout=request_timeout,
        )
        if not response.choices:
            raise _unexpected_response_error(response)
        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason == "length":
            logger.warning(
                f"[OpenAI] 输出被 max_tokens 截断 model={opts.model or self._model} "
                f"max_tokens={opts.max_tokens}（推理模型需为 reasoning_content 预留 token）"
            )
        content = choice.message.content or ""
        if opts.usage_out is not None:
            opts.usage_out.update(_usage_dict(response.usage))
        logger.info(
            f"[OpenAI] model={self._model} finish={finish_reason} "
            f"tokens={response.usage.total_tokens if response.usage else '?'}"
        )
        return content

    async def chat_stream(self, messages: List[ChatMessage], options: Optional[ChatOptions] = None) -> AsyncIterator[str]:
        """流式对话，逐 chunk 返回文本"""
        if not self.is_available():
            raise RuntimeError("OpenAI provider is not available")

        opts = options or ChatOptions()
        stream = await self._client.chat.completions.create(
            model=opts.model or self._model,
            messages=[_message_payload(m) for m in messages],
            temperature=opts.temperature,
            max_tokens=opts.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def chat_with_tools(
        self,
        messages: List[ChatMessage],
        tools: List[dict],
        options: Optional[ChatOptions] = None,
    ) -> ChatWithToolsResult:
        if not self.is_available():
            raise RuntimeError("OpenAI provider is not available")

        import json as _json

        opts = options or ChatOptions()
        formatted_msgs = [_message_payload(m) for m in messages]

        request_timeout = opts.timeout or self._timeout
        logger.info(f"[OpenAI tools] Sending request: model={self._model}, msgs={len(formatted_msgs)}, tools={len(tools) if tools else 0}, temp={opts.temperature}, max_tokens={opts.max_tokens}")

        # Build request kwargs - only include parameters the model supports
        create_kwargs: dict = {
            "model": opts.model or self._model,
            "messages": formatted_msgs,
        }
        if tools:
            create_kwargs["tools"] = tools
        
        # Strategy: try with full params first, then strip down on failure
        param_sets = [
            {"temperature": opts.temperature, "max_tokens": opts.max_tokens},  # full
            {},  # minimal - no temp/max_tokens
        ]
        
        last_error = None
        for i, extra_params in enumerate(param_sets):
            try_kwargs = {**create_kwargs, **extra_params}
            try:
                logger.info(f"[OpenAI tools] Attempt {i+1}: extra_keys={list(extra_params.keys()) or 'none'}")
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(**try_kwargs),
                    timeout=request_timeout,
                )
                # Success
                if not response.choices:
                    raise _unexpected_response_error(response)
                choice = response.choices[0]
                logger.info(f"[OpenAI tools] model={self._model} finish={choice.finish_reason} tokens={response.usage.total_tokens if response.usage else '?'}")
                break
            except Exception as e:
                last_error = e
                logger.warning(f"[OpenAI tools] Attempt {i+1} failed: {e}")
                # Log request body for 400 errors to help diagnose
                if '400' in str(e):
                    logger.error(f"[OpenAI tools] 400 error - request body: {_json.dumps(try_kwargs, ensure_ascii=False, default=str)}")
                if i < len(param_sets) - 1:
                    logger.info(f"[OpenAI tools] Retrying with simplified params...")
                else:
                    logger.error(f"[OpenAI tools] All attempts failed")
                    raise
        else:
            # This shouldn't happen since we either break or raise inside the loop
            raise last_error  # type: ignore
        result = ChatWithToolsResult()
        result.thinking = _reasoning_content(choice.message)
        if choice.message.content:
            result.text = choice.message.content
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = _json.loads(tc.function.arguments)
                except _json.JSONDecodeError:
                    args = {}
                result.tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))
        if response.usage:
            usage = _usage_dict(response.usage)
            result.usage = TokenUsage(
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
                cached_tokens=usage["cached_tokens"],
            )
        return result
