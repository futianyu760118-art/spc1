"""Tool 注册表 — 助手暴露给 LLM 的工具定义与注册（仅执行面智能体工具）"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolDef:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    execute: Callable  # async (db, params) -> dict
    # 元数据
    display_name: Optional[str] = None  # 显示名称
    keywords: List[str] = field(default_factory=list)  # 关键词列表
    category: Optional[str] = None  # 工具分类
    read_only: bool = True  # 只读工具直接执行；写工具须经确认门禁
    requires_confirmation: bool = False  # 写操作执行前必须人工确认


# 全局工具注册表
TOOL_REGISTRY: Dict[str, ToolDef] = {}


def register_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    display_name: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    category: Optional[str] = None,
    read_only: bool = True,
    requires_confirmation: bool = False,
):
    """装饰器：注册一个查询工具"""
    def decorator(func: Callable):
        TOOL_REGISTRY[name] = ToolDef(
            name=name,
            description=description,
            parameters=parameters,
            execute=func,
            display_name=display_name or name,
            keywords=keywords or [],
            category=category,
            read_only=read_only,
            requires_confirmation=requires_confirmation,
        )
        logger.info(f"Tool registered: {name} (read_only={read_only})")
        return func
    return decorator


def get_tool(name: str) -> Optional[ToolDef]:
    return TOOL_REGISTRY.get(name)


def get_all_tools() -> List[ToolDef]:
    return list(TOOL_REGISTRY.values())
