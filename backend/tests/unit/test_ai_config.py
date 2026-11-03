"""ai_config 纯函数单测：类型校正 / 白名单 / 提示词渲染"""

import pytest

import app.services.assistant.agent_tools  # noqa: F401 — 触发智能体工具注册（单测不经 app.main 导入链）
from app.services.ai_config import (
    ASSISTANT_CONFIG_DEFS,
    EXECUTION_AGENT_CONFIG_DEFS,
    TOOLS_PLACEHOLDER,
    coerce_value,
    render_system_prompt,
    _validate,
)
def test_coerce_int_float_json():
    assert coerce_value(ASSISTANT_CONFIG_DEFS["max_tokens"], "4096") == 4096
    assert coerce_value(ASSISTANT_CONFIG_DEFS["temperature"], "0.5") == 0.5


def test_validate_log_level():
    with pytest.raises(ValueError):
        _validate(EXECUTION_AGENT_CONFIG_DEFS["log_level"], "verbose")


def test_render_system_prompt_placeholder():
    template = f"头部\n{TOOLS_PLACEHOLDER}\n尾部"
    rendered = render_system_prompt(template, [])
    assert "头部" in rendered and "尾部" in rendered
    assert "- call_query_agent:" in rendered  # 智能体工具已注册（conftest 导入链）
    disabled_rendered = render_system_prompt(template, ["call_query_agent"])
    assert "- call_query_agent:" not in disabled_rendered


def test_render_system_prompt_without_placeholder_untouched():
    assert render_system_prompt("无占位符", ["x"]) == "无占位符"
