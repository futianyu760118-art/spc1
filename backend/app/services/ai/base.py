"""统一 AI 服务层 — 抽象基类与数据结构"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Type

from pydantic import BaseModel


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatOptions:
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 30


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
        默认实现：调用 chat + json.loads + pydantic 校验，失败重试 1 次。
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
            # 尝试提取 JSON
            text = raw.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
            try:
                data = json.loads(text)
                return schema.model_validate(data)
            except (json.JSONDecodeError, Exception):
                if attempt == 0:
                    messages.append(ChatMessage(role="assistant", content=raw))
                    messages.append(ChatMessage(role="user", content="输出格式不正确，请严格输出纯 JSON，不要包含其他内容。"))
                    continue
                raise
