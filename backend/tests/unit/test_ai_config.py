"""ai_config 纯函数单测：类型校正 / 白名单 / 提示词渲染"""

import pytest

import app.services.assistant.tools  # noqa: F401 — 触发工具注册（单测不经 app.main 导入链）
from app.services.ai_config import (
    ASSISTANT_CONFIG_DEFS,
    EXECUTION_AGENT_CONFIG_DEFS,
    TOOLS_PLACEHOLDER,
    coerce_value,
    render_system_prompt,
    _validate,
)
from app.services.assistant.tool_registry import get_all_tools


def test_coerce_int_float_json():
    assert coerce_value(ASSISTANT_CONFIG_DEFS["max_tokens"], "4096") == 4096
    assert coerce_value(ASSISTANT_CONFIG_DEFS["temperature"], "0.5") == 0.5
    assert coerce_value(ASSISTANT_CONFIG_DEFS["disabled_tools"], '["a"]') == ["a"]
    with pytest.raises(ValueError):
        coerce_value(ASSISTANT_CONFIG_DEFS["disabled_tools"], '"just-a-string"')


def test_validate_disabled_tools_rejects_unknown():
    with pytest.raises(ValueError):
        _validate(ASSISTANT_CONFIG_DEFS["disabled_tools"], ["no_such_tool"])
    known = get_all_tools()[0].name
    assert _validate(ASSISTANT_CONFIG_DEFS["disabled_tools"], [known]) == [known]


def test_validate_log_level():
    with pytest.raises(ValueError):
        _validate(EXECUTION_AGENT_CONFIG_DEFS["log_level"], "verbose")


def test_render_system_prompt_placeholder():
    template = f"头部\n{TOOLS_PLACEHOLDER}\n尾部"
    rendered = render_system_prompt(template, [])
    assert "头部" in rendered and "尾部" in rendered
    assert "- search_orders:" in rendered  # 内置工具已注册（conftest 导入链）
    disabled_rendered = render_system_prompt(template, ["search_orders"])
    assert "- search_orders:" not in disabled_rendered


def test_render_system_prompt_without_placeholder_untouched():
    assert render_system_prompt("无占位符", ["x"]) == "无占位符"
