"""统一 AI 服务层 — 抽象基类与数据结构"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Type

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    # DeepSeek thinking 模式：带 tool_calls 的 assistant 消息必须原样回传，否则下一轮 400
    reasoning_content: Optional[str] = None


@dataclass
class ChatOptions:
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 30
    model: Optional[str] = None  # 运行时配置覆盖；None=用 provider 构造时的 env 模型
    # 由 provider 在本次调用完成后填充真实 Token 用量（调用方传入可变 dict 回收）
    usage_out: Optional[Dict[str, Any]] = None


@dataclass
class ToolCall:
    """LLM 返回的工具调用请求"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolResult:
    """工具执行结果，回传给 LLM"""
    tool_call_id: str
    name: str
    content: str  # JSON string


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0  # 输入缓存命中 token（DeepSeek 计价：命中按缓存价计费）


@dataclass
class ChatWithToolsResult:
    """chat_with_tools 的返回值"""
    text: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Optional[TokenUsage] = None
    thinking: Optional[str] = None


class NotSupportedError(Exception):
    """Provider 不支持此操作"""
    pass


def _extract_json_object(raw: str) -> dict:
    """从 LLM 原始输出中提取 JSON 对象，兼容纯 JSON / markdown 代码块 / 带说明文字的 markdown 报告。

    提取策略（依次尝试）：
    1. 去首尾空白后直接 json.loads（裸 JSON）
    2. 剥离 markdown 代码块围栏（```json ... ``` 或 ``` ... ```）后 json.loads
    3. 取首个 '{' 到末个 '}' 之间的子串 json.loads（JSON 埋在说明文字中）
    全部失败则抛 json.JSONDecodeError。
    """
    import json as _json

    text = raw.strip()

    # 策略 1：直接解析
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        pass

    # 策略 2：剥离 markdown 围栏
    fenced = text
    if fenced.startswith("```"):
        lines = fenced.split("\n")
        if len(lines) > 2:
            inner = lines[1:]
            if inner and inner[-1].strip().startswith("```"):
                inner = inner[:-1]
            fenced = "\n".join(inner).strip()
        try:
            return _json.loads(fenced)
        except _json.JSONDecodeError:
            pass

    # 策略 3：首尾大括号截取
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return _json.loads(candidate)
        except _json.JSONDecodeError:
            pass

    raise _json.JSONDecodeError("未能从模型输出中提取到有效 JSON", raw, 0)


class LLMProvider(ABC):
    """LLM Provider 抽象基类，所有 provider 实现此接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 标识名"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """当前 provider 是否可用（已安装依赖 + 已配置 Key 等）"""
        ...

    @abstractmethod
    async def chat(self, messages: List[ChatMessage], options: Optional[ChatOptions] = None) -> str:
        """多轮对话，返回 assistant 文本"""
        ...

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        options: Optional[ChatOptions] = None,
    ) -> AsyncIterator[str]:
        """流式对话，逐 token 返回文本。默认实现：调用 chat 后一次性 yield。"""
        result = await self.chat(messages, options)
        yield result

    async def chat_with_tools(
        self,
        messages: List[ChatMessage],
        tools: List[Dict[str, Any]],
        options: Optional[ChatOptions] = None,
    ) -> ChatWithToolsResult:
        """带工具定义的对话，LLM 可选择调用工具或直接回复。
        默认实现抛 NotSupportedError，由具体 provider 覆盖。"""
        raise NotSupportedError(f"{self.name} 不支持 chat_with_tools")

    async def structured_output(
        self,
        prompt: str,
        schema: Type[BaseModel],
        options: Optional[ChatOptions] = None,
    ) -> BaseModel:
        """调用 LLM 并将输出解析为指定 pydantic schema 实例。
        默认实现：调用 chat + 多策略 JSON 提取 + pydantic 校验，失败重试 1 次。
        """
        import json

        system_msg = (
            "你是一个 JSON 输出助手。请严格按照以下 JSON Schema 输出，不要包含任何其他文字：\n"
            f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
        )
        messages = [
            ChatMessage(role="system", content=system_msg),
            ChatMessage(role="user", content=prompt),
        ]

        for attempt in range(2):
            raw = await self.chat(messages, options)
            try:
                data = _extract_json_object(raw)
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValueError, Exception) as e:
                logger.warning(
                    "[structured_output] 解析失败 attempt=%d provider=%s error=%s",
                    attempt + 1, self.name, e,
                )
                logger.warning(
                    "[structured_output] 原始输出前1000字符:\n%s",
                    raw[:1000] if raw else "(空)",
                )
                if attempt == 0:
                    messages.append(ChatMessage(role="assistant", content=raw))
                    messages.append(ChatMessage(role="user", content="输出格式不正确，请严格输出纯 JSON，不要包含其他内容、不要使用 markdown 代码块。"))
                    continue
                raise
