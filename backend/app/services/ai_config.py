"""智能体运行时配置中心 — DB 单点，env/代码常量为兜底默认值

设计文档：docs/superpowers/specs/2026-10-15-ai-agents-management-design.md
- 键白名单校验（两个 scope 各自合法键集，拒绝任意键注入）
- 每 scope 维护保留键 meta.version，保存即 +1，agent 侧版本比对用
- 提示词支持 {{TOOLS}} 占位符，构建时注入启用工具清单（防启停漂移）
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.models.basicdata.ai_agent import AiAgentConfig
from app.services.assistant.tool_registry import get_all_tools

ASSISTANT_SCOPE = "assistant"
EXECUTION_AGENT_SCOPE = "execution_agent"
EXECUTION_QUERY_SCOPE = "execution_query"
EXECUTION_REASONING_SCOPE = "execution_reasoning"
EXECUTION_ORDER_SCOPE = "execution_order"
VERSION_KEY = "meta.version"
TOOLS_PLACEHOLDER = "{{TOOLS}}"

EXECUTION_SCOPE_BY_AGENT = {
    "query": EXECUTION_QUERY_SCOPE,
    "reasoning": EXECUTION_REASONING_SCOPE,
    "order": EXECUTION_ORDER_SCOPE,
}


@dataclass
class ConfigDef:
    key: str
    value_type: str  # string | int | float | bool | json
    default: Any
    label: str
    description: str = ""


ASSISTANT_CONFIG_DEFS: Dict[str, ConfigDef] = {
    "system_prompt": ConfigDef("system_prompt", "string", "", "系统提示词",
                               "留空使用内置默认；支持 {{TOOLS}} 占位符自动注入启用工具清单"),
    "intent_prompt": ConfigDef("intent_prompt", "string", "", "意图识别提示词", "留空使用内置默认"),
    "model_name": ConfigDef("model_name", "string", "", "模型名", "留空使用 .env 默认模型"),
    "temperature": ConfigDef("temperature", "float", 0.1, "温度"),
    "max_tokens": ConfigDef("max_tokens", "int", 4096, "最大输出 token"),
    "max_tool_rounds": ConfigDef("max_tool_rounds", "int", 5, "工具循环轮数上限"),
    "tool_execute_timeout": ConfigDef("tool_execute_timeout", "int", 30, "工具执行超时（秒）"),
    "disabled_tools": ConfigDef("disabled_tools", "json", [], "禁用工具列表", "JSON 数组"),
    "routing_enabled": ConfigDef("routing_enabled", "bool", True, "任务路由开关",
                                 "开启后助手优先把任务派给本系统执行面智能体，未命中时预览 Hub 路由"),
}

def _execution_common_defs() -> Dict[str, ConfigDef]:
    return {
        "agent_name": ConfigDef("agent_name", "string", "", "注册显示名", "留空使用 env"),
        "ws_url": ConfigDef("ws_url", "string", "", "Hub WebSocket 地址", "留空使用 env"),
        "agent_id": ConfigDef("agent_id", "string", "", "Agent ID", "留空使用 env"),
        "log_level": ConfigDef("log_level", "string", "info", "日志级别", "debug|info|warn|error"),
    }


EXECUTION_QUERY_CONFIG_DEFS: Dict[str, ConfigDef] = {
    **_execution_common_defs(),
    "query_timeout_ms": ConfigDef("query_timeout_ms", "int", 15000, "查询超时（ms）"),
}

EXECUTION_REASONING_CONFIG_DEFS: Dict[str, ConfigDef] = {
    **_execution_common_defs(),
    "reasoning_timeout_ms": ConfigDef("reasoning_timeout_ms", "int", 180000, "推理超时（ms）",
                                      "变更需同步关注中台 REASONING_TIMEOUT_S 约束"),
}

EXECUTION_ORDER_CONFIG_DEFS: Dict[str, ConfigDef] = {
    **_execution_common_defs(),
    "write_timeout_ms": ConfigDef("write_timeout_ms", "int", 15000, "写请求超时（ms）"),
}

EXECUTION_AGENT_CONFIG_DEFS: Dict[str, ConfigDef] = {
    "agent_name": ConfigDef("agent_name", "string", "", "注册显示名", "留空使用 env"),
    "ws_url": ConfigDef("ws_url", "string", "", "Hub WebSocket 地址", "留空使用 env"),
    "agent_id": ConfigDef("agent_id", "string", "", "Agent ID", "留空使用 env"),
    "query_timeout_ms": ConfigDef("query_timeout_ms", "int", 15000, "查询超时（ms）"),
    "reasoning_timeout_ms": ConfigDef("reasoning_timeout_ms", "int", 180000, "推理超时（ms）",
                                      "变更需同步关注中台 REASONING_TIMEOUT_S 约束"),
    "log_level": ConfigDef("log_level", "string", "info", "日志级别", "debug|info|warn|error"),
}

SCOPE_DEFS: Dict[str, Dict[str, ConfigDef]] = {
    ASSISTANT_SCOPE: ASSISTANT_CONFIG_DEFS,
    EXECUTION_AGENT_SCOPE: EXECUTION_AGENT_CONFIG_DEFS,
    EXECUTION_QUERY_SCOPE: EXECUTION_QUERY_CONFIG_DEFS,
    EXECUTION_REASONING_SCOPE: EXECUTION_REASONING_CONFIG_DEFS,
    EXECUTION_ORDER_SCOPE: EXECUTION_ORDER_CONFIG_DEFS,
}


def coerce_value(def_: ConfigDef, raw: Any) -> Any:
    try:
        if def_.value_type == "int":
            return int(raw)
        if def_.value_type == "float":
            return float(raw)
        if def_.value_type == "bool":
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in ("1", "true", "yes")
        if def_.value_type == "json":
            if isinstance(raw, (list, dict)):
                return raw
            parsed = json.loads(raw)
            if not isinstance(parsed, (list, dict)):
                raise ValueError("必须是 JSON 数组或对象")
            return parsed
        return "" if raw is None else str(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"配置 {def_.key} 值非法：{e}") from e


def _validate(def_: ConfigDef, value: Any) -> Any:
    value = coerce_value(def_, value)
    if def_.key == "disabled_tools":
        known = {t.name for t in get_all_tools()}
        unknown = [t for t in value if t not in known]
        if unknown:
            raise ValueError(f"未知工具: {unknown}")
    if def_.key == "log_level" and value not in ("debug", "info", "warn", "error"):
        raise ValueError("log_level 必须是 debug|info|warn|error")
    if def_.key == "query_timeout_ms" and not (1000 <= value <= 120000):
        raise ValueError("query_timeout_ms 必须在 1000-120000 之间")
    if def_.key == "reasoning_timeout_ms" and not (10000 <= value <= 600000):
        raise ValueError("reasoning_timeout_ms 必须在 10000-600000 之间")
    if def_.key == "write_timeout_ms" and not (1000 <= value <= 120000):
        raise ValueError("write_timeout_ms 必须在 1000-120000 之间")
    if def_.value_type == "string":
        limit = 20000 if def_.key in ("system_prompt", "intent_prompt") else 500
        if len(value) > limit:
            raise ValueError(f"配置 {def_.key} 超长：{len(value)} 字符 > 上限 {limit}")
    return value


def _to_stored(def_: ConfigDef, value: Any) -> str:
    if def_.value_type == "json":
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


async def get_scope_config(db: AsyncSession, scope: str) -> Dict[str, Any]:
    """DB 行覆盖默认值；无行/空值 → 代码默认（提示词空串由消费方回退内置常量）"""
    defs = SCOPE_DEFS[scope]
    result = await db.execute(
        select(AiAgentConfig.config_key, AiAgentConfig.config_value).where(AiAgentConfig.scope == scope)
    )
    overrides = {row.config_key: row.config_value for row in result}
    config: Dict[str, Any] = {}
    for key, def_ in defs.items():
        raw = overrides.get(key)
        config[key] = def_.default if raw is None else coerce_value(def_, raw)
    return config


async def get_scope_version(db: AsyncSession, scope: str) -> int:
    result = await db.execute(
        select(AiAgentConfig.config_value).where(
            AiAgentConfig.scope == scope, AiAgentConfig.config_key == VERSION_KEY
        )
    )
    row = result.scalar_one_or_none()
    try:
        return int(row) if row is not None else 0
    except (TypeError, ValueError):
        return 0


def operator_name(current_user) -> str:
    """审计操作人：username 优先，回退 user_id/sub（current_user 为 JWT payload dict）"""
    username = current_user.get("username") if isinstance(current_user, dict) else getattr(current_user, "username", None)
    if username:
        return str(username)
    user_id = (
        current_user.get("user_id") or current_user.get("sub")
        if isinstance(current_user, dict)
        else (getattr(current_user, "user_id", None) or getattr(current_user, "id", None))
    )
    return str(user_id) if user_id is not None else ""


async def _upsert_config_row(
    db: AsyncSession, scope: str, key: str, stored: str, value_type: str, updated_by: str
) -> None:
    await db.execute(
        pg_insert(AiAgentConfig)
        .values(scope=scope, config_key=key, config_value=stored,
                value_type=value_type, updated_by=updated_by)
        .on_conflict_do_update(
            constraint="uq_ai_agent_config_scope_key",
            set_={"config_value": stored, "value_type": value_type,
                  "updated_by": updated_by, "updated_at": func.now()},
        )
    )


async def save_scope_config(db: AsyncSession, scope: str, values: Dict[str, Any], updated_by: str) -> int:
    """白名单校验 + 类型校正 + 逐键 upsert + 审计 + 版本 +1；异常抛 ValueError 由端点转信封"""
    defs = SCOPE_DEFS[scope]
    unknown = [k for k in values if k not in defs]
    if unknown:
        raise ValueError(f"不支持的配置键: {unknown}（合法键: {sorted(defs)}）")

    for key, raw in values.items():
        def_ = defs[key]
        value = _validate(def_, raw)
        stored = _to_stored(def_, value)
        await _upsert_config_row(db, scope, key, stored, def_.value_type, updated_by)
        await log_audit(db, "ai_agent_config", 0, "update", field_name=f"{scope}.{key}",
                        new_value=stored[:500] if stored else None, operator=updated_by)

    version = await get_scope_version(db, scope) + 1
    await _upsert_config_row(db, scope, VERSION_KEY, str(version), "int", updated_by)
    return version


def render_system_prompt(template: str, disabled_tools: Optional[List[str]] = None) -> str:
    """{{TOOLS}} 占位符 → 启用工具的 `- name: description` 清单；模板不含占位符则原样返回"""
    if TOOLS_PLACEHOLDER not in template:
        return template
    disabled = set(disabled_tools or [])
    lines = [f"- {t.name}: {t.description}" for t in get_all_tools() if t.name not in disabled]
    return template.replace(TOOLS_PLACEHOLDER, "\n".join(lines))


async def get_agent_external_config(db: AsyncSession, agent_key: Optional[str] = None) -> Dict[str, Any]:
    """agent 拉取用：按 agent_key 选 scope，只下发显式保存的非空值（空=agent 继续用 env）。"""
    if agent_key:
        scope = EXECUTION_SCOPE_BY_AGENT.get(agent_key)
        if scope is None:
            raise ValueError(f"未知 agent: {agent_key}")
    else:
        scope = EXECUTION_AGENT_SCOPE
    result = await db.execute(
        select(AiAgentConfig.config_key, AiAgentConfig.config_value).where(AiAgentConfig.scope == scope)
    )
    saved_keys = [
        row.config_key
        for row in result
        if row.config_key != VERSION_KEY and row.config_value not in ("", None)
    ]
    full = await get_scope_config(db, scope)
    config = {key: full[key] for key in saved_keys if key in full}
    version = await get_scope_version(db, scope)
    return {"version": version, "config": config}
