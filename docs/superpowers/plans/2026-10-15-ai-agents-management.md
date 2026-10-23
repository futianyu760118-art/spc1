# 智能助手与执行面智能体管理台 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为中台智能助手（工具启停/模型与提示词/用量统计/日志监控）与 aeos-execution-agent（配置可编辑/远程自重启）建 SystemCenter 前端管理台，配置存 DB（方案 A）。

**Architecture:** 配置单点在 `ai_agent_config` 表（scope 区分），env 退化为默认/引导值；助手侧每请求读 DB 即时生效；agent 启动/自重启时经既有 HMAC 外部 API（新端点码 `agent.config`）拉取；backend 经 `x-admin-token` 代理调 agent `/admin/*`；用量审计落 `assistant_run` 表。

**Tech Stack:** FastAPI + SQLAlchemy(async) + PostgreSQL（后端）；Ant Design 5 + @ant-design/charts（前端）；Node 20 原生 http/ws（agent）。

**设计文档:** `docs/superpowers/specs/2026-10-15-ai-agents-management-design.md`

## Global Constraints

- 响应必须 `{code, message, data}` 信封（`ResponseModel`），前端拦截器判 `code !== 0` 为失败
- 新表只走 `create_all`（models 注册进 `app/models/__init__.py`），不写 Alembic；本特性无加列需求，`init_database.py` 无需改
- 敏感值（appSecret、EXECUTION_PLANE_TOKEN、AGENT_ADMIN_TOKEN、platformBaseUrl、AI API Key）永不进 DB、不回显
- ERP 同步守卫、审批引擎、索赔单代码不碰；改完必须 `python -m pytest`（后端）+ `npm run build`（前端）
- pytest 的 `asyncio_default_fixture_loop_scope = session` 两行是硬性前提，禁止改动
- 前端无 lint/test 脚本，`npm run build` 是唯一校验；路径别名 `@` → `src/`
- agent 侧查询白名单三处同步约束不受本计划影响（不改 `query-adapter.js` 映射）
- 每个任务完成后按仓库风格提交一次 commit（`feat(ai-agents): ...`）
- 权限菜单可见性偏差说明：`ai.assistant_config` 不挂 route_path，采用 approval.business 模式（页内 Tab 级校验）；仅授予 config 而无 monitor 的角色看不到菜单入口 —— 授角色时两者一起授（与审批中心 `approval.business` 需 `approval.config` 才能进页同一先例，偏离设计文档 §7.1 的「任一即显示」，记录于此）

---

## 阶段 1 · 后端数据模型与配置服务

### Task 1.1 — 新建模型 `ai_agent_config` + `assistant_run`

文件：`backend/app/models/basicdata/ai_agent.py`（新建）

```python
"""基础数据与集成中心 — 智能体运行时配置与助手用量审计模型（管理台 2026-10 版）"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class AiAgentConfig(Base):
    """智能体运行时配置（scope='assistant' | 'execution_agent'），env 为兜底默认值"""

    __tablename__ = "ai_agent_config"
    __table_args__ = (
        UniqueConstraint("scope", "config_key", name="uq_ai_agent_config_scope_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(32), nullable=False, comment="assistant | execution_agent")
    config_key = Column(String(64), nullable=False, comment="配置键（白名单校验）")
    config_value = Column(Text, nullable=True, comment="配置值（空=回退代码默认）")
    value_type = Column(String(8), nullable=False, default="string", comment="string|int|float|bool|json")
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class AssistantRun(Base):
    """智能助手单次对话用量审计（chat 与 SSE 流式各落一条）"""

    __tablename__ = "assistant_run"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True, index=True)
    user_message = Column(String(500), nullable=True)
    intent = Column(String(32), nullable=True, comment="query_data|analyze_history|general_chat|agent|unknown")
    tools_called = Column(JSONB, nullable=True, comment="工具名数组（按调用序去重）")
    tool_rounds = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Numeric(12, 2), nullable=True)
    is_success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
```

文件：`backend/app/models/__init__.py` — 在 `from app.models.basicdata.backup import ...` 行（约 68 行）后加：

```python
from app.models.basicdata.ai_agent import AiAgentConfig, AssistantRun  # noqa: F401
```

并在 `__all__` 的 `"BackupConfig", "BackupRecord",` 之后（基础数据段落）加：

```python
    "AiAgentConfig",
    "AssistantRun",
```

验证：

```bash
cd backend && python -c "from app.models import AiAgentConfig, AssistantRun; print('ok')"
```

commit: `feat(ai-agents): ai_agent_config/assistant_run 数据模型`

### Task 1.2 — 配置中心服务 `app/services/ai_config.py`

文件：`backend/app/services/ai_config.py`（新建，完整内容）

```python
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
VERSION_KEY = "meta.version"
TOOLS_PLACEHOLDER = "{{TOOLS}}"


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
        await db.execute(
            pg_insert(AiAgentConfig)
            .values(scope=scope, config_key=key, config_value=stored,
                    value_type=def_.value_type, updated_by=updated_by)
            .on_conflict_do_update(
                constraint="uq_ai_agent_config_scope_key",
                set_={"config_value": stored, "value_type": def_.value_type,
                      "updated_by": updated_by, "updated_at": func.now()},
            )
        )
        await log_audit(db, "ai_agent_config", 0, "update", field_name=f"{scope}.{key}",
                        new_value=stored[:500] if stored else None, operator=updated_by)

    version = await get_scope_version(db, scope) + 1
    await db.execute(
        pg_insert(AiAgentConfig)
        .values(scope=scope, config_key=VERSION_KEY, config_value=str(version),
                value_type="int", updated_by=updated_by)
        .on_conflict_do_update(
            constraint="uq_ai_agent_config_scope_key",
            set_={"config_value": str(version), "updated_by": updated_by, "updated_at": func.now()},
        )
    )
    return version


def render_system_prompt(template: str, disabled_tools: Optional[List[str]] = None) -> str:
    """{{TOOLS}} 占位符 → 启用工具的 `- name: description` 清单；模板不含占位符则原样返回"""
    if TOOLS_PLACEHOLDER not in template:
        return template
    disabled = set(disabled_tools or [])
    lines = [f"- {t.name}: {t.description}" for t in get_all_tools() if t.name not in disabled]
    return template.replace(TOOLS_PLACEHOLDER, "\n".join(lines))


async def get_agent_external_config(db: AsyncSession) -> Dict[str, Any]:
    """agent 拉取用：仅非空值下发（空=agent 继续用 env），附版本号"""
    config = await get_scope_config(db, EXECUTION_AGENT_SCOPE)
    version = await get_scope_version(db, EXECUTION_AGENT_SCOPE)
    return {"version": version, "config": {k: v for k, v in config.items() if v not in ("", None)}}
```

注意：`log_audit` 只 flush 不 commit，与 `get_db()` 成功自动 commit 的约定一致。

验证：

```bash
cd backend && python -c "from app.services.ai_config import ASSISTANT_CONFIG_DEFS, render_system_prompt; print(len(ASSISTANT_CONFIG_DEFS))"
```

commit: `feat(ai-agents): 运行时配置中心服务（白名单/版本/提示词渲染）`

### Task 1.3 — 权限声明与角色授权

文件：`backend/app/core/permission_registry.py` — 在「备份管理」声明块（约 384-390 行）之后加：

```python
# 智能体管理台（2026-10-15）— 智能助手监控/配置 + 执行面智能体管理
declare_permission(
    "ai.assistant_monitor", "智能助手管理",
    module="basicdata", parent_code="basicdata",
    actions=["read"],
    route_path="/ai-assistant", sort_order=13,
)
# Tab 级权限（页内二次校验，同 approval.business 模式；无独立路由）
declare_permission(
    "ai.assistant_config", "助手配置",
    module="basicdata", parent_code="ai.assistant_monitor",
    actions=["read", "update"], sort_order=1,
)
declare_permission(
    "ai.execution_agent", "执行面智能体",
    module="basicdata", parent_code="basicdata",
    actions=["read", "update"],
    route_path="/execution-agent", sort_order=14,
)
```

文件：`backend/app/core/permissions.py` — `ROLE_PERMISSION_ADDITIONS["admin"]` 字典内（`"backup": ...` 行后）加：

```python
        "ai.assistant_monitor": ["read"],
        "ai.assistant_config": ["read", "update"],
        "ai.execution_agent": ["read", "update"],
```

验证：

```bash
cd backend && python -c "from app.core.permission_registry import get_all_declared_permissions; assert 'ai.assistant_monitor' in get_all_declared_permissions(); print('ok')"
```

commit: `feat(ai-agents): ai.assistant_monitor/assistant_config/execution_agent 权限声明`

### Task 1.4 — Settings 增项

文件：`backend/app/core/config.py` — 在 `REASONING_MAX_CONCLUSIONS` 行（约 115 行）后加：

```python
    # 智能体管理台（backend 代理访问执行面 agent 的 admin 面；两者留空则 status/restart 返回下线态）
    EXECUTION_AGENT_BASE_URL: str = ""   # 如 http://aeos-execution-agent:8790
    AGENT_ADMIN_TOKEN: str = ""          # 与 agent .env 的 AGENT_ADMIN_TOKEN 一致
```

验证：

```bash
cd backend && python -c "from app.core.config import get_settings; print(bool(get_settings().EXECUTION_AGENT_BASE_URL is not None))"
```

commit: `feat(ai-agents): Settings 增执行面 agent 代理地址与管理令牌`

---

## 阶段 2 · 助手侧后端

### Task 2.1 — ChatOptions 支持按请求覆盖模型

文件：`backend/app/services/ai/base.py` — `ChatOptions` 增加字段：

```python
@dataclass
class ChatOptions:
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 30
    model: Optional[str] = None  # 运行时配置覆盖；None=用 provider 构造时的 env 模型
```

文件：`backend/app/services/ai/openai_provider.py` — 三处 `model=self._model` 改为 `model=opts.model or self._model`：
- `chat()` 内 `create(model=self._model, ...)`（约 66 行）
- `chat_stream()` 内 `create(model=self._model, ...)`（约 86 行）
- `chat_with_tools()` 内 `create_kwargs: dict = {"model": self._model, ...}`（约 123 行）改为 `"model": opts.model or self._model,`

文件：`backend/app/services/ai/dashscope_provider.py` — 同样把三处 `model=self._model` 改为 `model=(opts.model if opts and opts.model else self._model)`（`chat` / `chat_stream` / `chat_with_tools` 各一处，约 51/81/126 行）。

验证：

```bash
cd backend && python -c "from app.services.ai.base import ChatOptions; assert ChatOptions(model='x').model == 'x'; print('ok')"
```

commit: `feat(ai-agents): ChatOptions 增 model 覆盖，providers 尊重运行时模型名`

### Task 2.2 — tool_registry 过滤参数

文件：`backend/app/services/assistant/tool_registry.py` — `get_openai_tools_schema` 改为：

```python
def get_openai_tools_schema(exclude: Optional[set] = None) -> List[Dict[str, Any]]:
    """将注册表转为 OpenAI function calling 的 tools 格式；exclude 为运行时禁用的工具名集合"""
    excluded = exclude or set()
    tools = []
    for tool in TOOL_REGISTRY.values():
        if tool.name in excluded:
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        })
    return tools
```

验证：

```bash
cd backend && python -c "
import app.services.assistant.tools
from app.services.assistant.tool_registry import get_openai_tools_schema
n = len(get_openai_tools_schema())
assert n > 0 and len(get_openai_tools_schema(exclude={t['function']['name'] for t in get_openai_tools_schema()})) == 0
print(n)"
```

commit: `feat(ai-agents): 工具 schema 支持禁用过滤`

### Task 2.3 — agent.py 接入运行时配置

文件：`backend/app/services/assistant/agent.py`，改动点（保持既有结构，逐点小改）：

1. import 区加：

```python
from app.services.ai_config import (
    ASSISTANT_SCOPE,
    get_scope_config,
    render_system_prompt,
)
```

2. 模块级加辅助（`TOOL_RETRY_CONFIG` 之后）：

```python
async def _load_runtime_config(db: AsyncSession) -> Dict[str, Any]:
    """每次请求读 DB 配置（无缓存，多实例强一致）；读失败回退默认值不阻断对话"""
    from app.services.ai_config import ASSISTANT_CONFIG_DEFS
    try:
        return await get_scope_config(db, ASSISTANT_SCOPE)
    except Exception as e:
        logger.warning(f"[agent] 读取运行时配置失败，使用默认值: {e}")
        return {k: d.default for k, d in ASSISTANT_CONFIG_DEFS.items()}
```

3. `_recognize_intent` 增可选参（默认 None 用模块常量，agent_stream 复用不受影响）：

```python
async def _recognize_intent(
    message: str,
    history: List[Dict[str, Any]],
    intent_prompt: Optional[str] = None,
) -> str:
    try:
        messages = [ChatMessage(role="system", content=intent_prompt or INTENT_RECOGNITION_PROMPT)]
```

（函数其余不变）

4. `_execute_tool_with_retry` 增可选参并在入口拦截禁用工具：

```python
async def _execute_tool_with_retry(
    db: AsyncSession,
    tool_name: str,
    params: Dict[str, Any],
    timeout: int = TOOL_EXECUTE_TIMEOUT,
    disabled_tools: Optional[set] = None,
) -> Dict[str, Any]:
    from app.services.assistant.tool_registry import get_tool

    if disabled_tools and tool_name in disabled_tools:
        return {"error": f"工具 {tool_name} 已被管理员禁用"}
    tool_def = get_tool(tool_name)
    ...
```

并把函数体内 `timeout=TOOL_EXECUTE_TIMEOUT` 改为 `timeout=timeout`。

5. `run()` 内（`settings = get_settings()` 之后）加：

```python
    rt = await _load_runtime_config(db)
    disabled = set(rt.get("disabled_tools") or [])
    system_prompt = render_system_prompt(rt.get("system_prompt") or SYSTEM_PROMPT, disabled)
    intent_prompt = (rt.get("intent_prompt") or "").strip() or None
    main_options = ChatOptions(
        temperature=rt.get("temperature", 0.1),
        max_tokens=rt.get("max_tokens", 4096),
        model=(rt.get("model_name") or "").strip() or None,
    )
```

6. `run()` 内全部替换点：
- `intent = await _recognize_intent(message, history)` → `_recognize_intent(message, history, intent_prompt)`
- 两处 `ChatMessage(role="system", content=SYSTEM_PROMPT)`（ANALYZE_HISTORY 路径与 QUERY_DATA 路径）→ `content=system_prompt`
- ANALYZE_HISTORY 路径 `options = ChatOptions(temperature=0.3, max_tokens=4096, timeout=60)` → `options = ChatOptions(temperature=main_options.temperature, max_tokens=main_options.max_tokens, model=main_options.model, timeout=60)`
- QUERY_DATA 路径 `options = ChatOptions(temperature=0.1, max_tokens=4096, timeout=120)` → `options = ChatOptions(temperature=main_options.temperature, max_tokens=main_options.max_tokens, model=main_options.model, timeout=120)`
- `tools_schema = get_openai_tools_schema()` → `tools_schema = get_openai_tools_schema(exclude=disabled)`
- `for round_idx in range(MAX_TOOL_ROUNDS):` → `for round_idx in range(rt.get("max_tool_rounds", MAX_TOOL_ROUNDS)):`
- `data = await _execute_tool_with_retry(db, tc.name, tc.arguments)` → `data = await _execute_tool_with_retry(db, tc.name, tc.arguments, timeout=rt.get("tool_execute_timeout", TOOL_EXECUTE_TIMEOUT), disabled_tools=disabled)`
- 捕获 usage 处（`if result.usage and result.usage.total_tokens: last_api_total_tokens = ...`）之后加一行：

```python
                diagnostics["total_tokens"] = last_api_total_tokens
```

验证：

```bash
cd backend && python -c "import app.services.assistant.agent as a; import inspect; assert 'intent_prompt' in inspect.signature(a._recognize_intent).parameters; print('ok')"
```

commit: `feat(ai-agents): 助手 Agent 接入 DB 运行时配置（提示词/模型/轮数/工具禁用）`

### Task 2.4 — agent_stream.py 接入运行时配置 + stats 事件

文件：`backend/app/services/assistant/agent_stream.py`，改动点：

1. import 区调整：

```python
from app.services.assistant.agent import (
    SYSTEM_PROMPT,
    _recognize_intent,
    _execute_tool_with_retry,
    _strip_think_tags,
    _extract_thinking,
    _load_runtime_config,
)
from app.services.ai_config import render_system_prompt
```

2. `run_stream()` 内（`settings = get_settings()` 之后）加：

```python
    rt = await _load_runtime_config(db)
    disabled = set(rt.get("disabled_tools") or [])
    system_prompt = render_system_prompt(rt.get("system_prompt") or SYSTEM_PROMPT, disabled)
    intent_prompt = (rt.get("intent_prompt") or "").strip() or None

    stats: Dict[str, Any] = {"tools_called": [], "tool_rounds": 0, "total_tokens": None}
```

3. 替换点（与 agent.py 同构）：
- `intent = await _recognize_intent(message, history)` → 带 `intent_prompt`
- 两处 `content=SYSTEM_PROMPT` → `content=system_prompt`
- ANALYZE_HISTORY 路径 `options = ChatOptions(temperature=0.3, max_tokens=4096, timeout=60)` → `ChatOptions(temperature=rt.get("temperature", 0.1), max_tokens=rt.get("max_tokens", 4096), model=(rt.get("model_name") or "").strip() or None, timeout=60)`
- QUERY_DATA 路径 `options = ChatOptions(temperature=0.1, max_tokens=4096, timeout=120)` → 同上 temperature/max_tokens/model，`timeout=120`
- `tools_schema = get_openai_tools_schema()` → `exclude=disabled`
- `for round_idx in range(MAX_TOOL_ROUNDS):` → `range(rt.get("max_tool_rounds", MAX_TOOL_ROUNDS))`
- `data = await _execute_tool_with_retry(db, tc.name, tc.arguments)` → 带 `timeout=rt.get("tool_execute_timeout", 30), disabled_tools=disabled`
- 工具循环内 `for tc in result.tool_calls:` 开头加统计：

```python
                if tc.name not in stats["tools_called"]:
                    stats["tools_called"].append(tc.name)
                stats["tool_rounds"] = round_idx + 1
```

- 每轮 `result` 返回后（run_logger 记录处附近）加：

```python
            if result.usage and result.usage.total_tokens:
                stats["total_tokens"] = result.usage.total_tokens
```

4. 终态 done 事件统一附 stats —— 三处 `yield _sse_event("done", {...})`（ANALYZE_HISTORY 路径两处含 error 后的 done、QUERY_DATA direct_reply 与 max_rounds 路径）payload 增加 `"stats": stats`，例如：

```python
            yield _sse_event("done", {"provider": provider_name, "intent": intent.lower(), "stats": stats})
```

（error 后紧跟的 done 也带 stats；rule_based 早退路径不带。）

验证：

```bash
cd backend && python -c "import app.services.assistant.agent_stream; print('ok')"
```

commit: `feat(ai-agents): 流式 Agent 接入运行时配置并透传用量 stats 事件`

### Task 2.5 — assistant_run 落库（routes 层收口）

文件：`backend/app/api/v1/assistant/routes.py`，改动：

1. import 区加：

```python
from app.models.basicdata.ai_agent import AssistantRun
```

2. 模块级辅助（`router = APIRouter()` 之后）：

```python
async def _record_run(
    db: AsyncSession,
    *,
    trace_id: str,
    session_id: str,
    user_id: str,
    message: str,
    intent: Optional[str],
    tools_called: list,
    tool_rounds: Optional[int],
    total_tokens: Optional[int],
    duration_ms: Optional[float],
    is_success: bool,
    error_message: Optional[str],
) -> None:
    """用量审计落库；失败仅告警不影响对话主流程"""
    try:
        db.add(AssistantRun(
            trace_id=trace_id or "",
            session_id=session_id or None,
            user_id=user_id or None,
            user_message=(message or "")[:500],
            intent=intent,
            tools_called=tools_called or None,
            tool_rounds=tool_rounds,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            is_success=is_success,
            error_message=error_message,
        ))
        await db.flush()
    except Exception as exc:
        logger.warning(f"[assistant] 用量落库失败 trace={trace_id}: {exc}")


def _diag_tools(diagnostics: Optional[dict]) -> list:
    if not diagnostics:
        return []
    names: list = []
    for item in diagnostics.get("tools") or []:
        name = item.get("name")
        if name and name not in names:
            names.append(name)
    return names
```

3. `chat()` 内 `return {"code": 0, ...}` 之前（total_duration_ms 已算好）插入：

```python
        errors = (reply.diagnostics or {}).get("errors") or []
        await _record_run(
            db,
            trace_id=trace_id, session_id=session_id, user_id=str(user_id), message=body.message,
            intent=(reply.diagnostics or {}).get("intent"),
            tools_called=_diag_tools(reply.diagnostics),
            tool_rounds=len((reply.diagnostics or {}).get("llm_rounds") or []),
            total_tokens=(reply.diagnostics or {}).get("total_tokens"),
            duration_ms=total_duration_ms,
            is_success=not errors,
            error_message=errors[0].get("message") if errors else None,
        )
```

4. `chat_stream()` 的 `event_generator` 改造为解析事件并落库：

```python
    async def event_generator():
        started = time.perf_counter()
        run_info: Dict[str, Any] = {"tools": [], "stats": None, "intent": None, "error": None, "done": False}

        def _track(raw_event: str) -> None:
            lines = raw_event.split("\n")
            event_name = next((l[7:] for l in lines if l.startswith("event: ")), "")
            data_line = next((l[6:] for l in lines if l.startswith("data: ")), None)
            if not data_line:
                return
            try:
                payload = json.loads(data_line)
            except Exception:
                return
            if event_name == "tool_start":
                name = payload.get("name")
                if name and name not in run_info["tools"]:
                    run_info["tools"].append(name)
            elif event_name == "done":
                run_info["done"] = True
                run_info["intent"] = payload.get("intent")
                run_info["stats"] = payload.get("stats")
            elif event_name == "error":
                run_info["error"] = payload.get("message")

        try:
            yield f"event: session\ndata: {json.dumps({'session_id': session_id, 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
            async for event in agent_stream.run_stream(
                message=body.message,
                db=db,
                session_id=session_id,
                conversation_history=body.conversation_history,
                trace_id=trace_id,
                user_id=str(user_id) if user_id else "",
                request=request,
            ):
                _track(event)
                yield event
        finally:
            stats = run_info["stats"] or {}
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            await _record_run(
                db,
                trace_id=trace_id, session_id=session_id, user_id=str(user_id), message=body.message,
                intent=run_info["intent"],
                tools_called=run_info["tools"],
                tool_rounds=stats.get("tool_rounds"),
                total_tokens=stats.get("total_tokens"),
                duration_ms=duration_ms,
                is_success=run_info["done"] and not run_info["error"],
                error_message=run_info["error"] or (None if run_info["done"] else "stream_interrupted"),
            )
```

（`import time` 已在文件头；`Dict/Any` 已在 typing import。）

验证：

```bash
cd backend && python -c "from app.api.v1.assistant.routes import _record_run, _diag_tools; print('ok')"
```

commit: `feat(ai-agents): 助手对话用量审计落库 assistant_run`

### Task 2.6 — 管理端点 `/api/v1/system/ai-assistant/*`

文件：`backend/app/api/v1/system/ai_assistant.py`（新建，完整内容）：

```python
"""系统管理 — 智能助手管理端点（监控 + 配置，设计文档 2026-10-15）"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.ai_config import (
    ASSISTANT_SCOPE,
    SCOPE_DEFS,
    get_scope_config,
    get_scope_version,
    save_scope_config,
)
from app.services.assistant.tool_registry import get_all_tools

router = APIRouter()


class AssistantConfigIn(BaseModel):
    config: dict


@router.get("/stats", response_model=ResponseModel[dict])
async def assistant_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.assistant_monitor", "read")),
):
    since = f"NOW() - INTERVAL '{days} days'"
    total_row = (await db.execute(text(
        f"SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN is_success THEN 1 ELSE 0 END),0) AS ok, "
        f"COALESCE(AVG(duration_ms),0) AS avg_ms, COALESCE(SUM(total_tokens),0) AS tokens, "
        f"COUNT(DISTINCT user_id) AS active_users FROM assistant_run WHERE created_at >= {since}"
    ))).mappings().first()
    trend = (await db.execute(text(
        f"SELECT to_char(created_at,'YYYY-MM-DD') AS day, COUNT(*) AS total, "
        f"SUM(CASE WHEN is_success THEN 1 ELSE 0 END) AS ok "
        f"FROM assistant_run WHERE created_at >= {since} GROUP BY day ORDER BY day"
    ))).mappings().all()
    top_tools = (await db.execute(text(
        f"SELECT tool, COUNT(*) AS hits FROM assistant_run, "
        f"jsonb_array_elements_text(tools_called) AS tool "
        f"WHERE created_at >= {since} GROUP BY tool ORDER BY hits DESC LIMIT 10"
    ))).mappings().all()
    return {
        "total": total_row["total"],
        "success": total_row["ok"],
        "success_rate": round(total_row["ok"] / total_row["total"], 4) if total_row["total"] else None,
        "avg_duration_ms": round(float(total_row["avg_ms"]), 1),
        "total_tokens": total_row["tokens"],
        "active_users": total_row["active_users"],
        "trend": [dict(r) for r in trend],
        "top_tools": [dict(r) for r in top_tools],
    }


@router.get("/runs", response_model=ResponseModel[dict])
async def assistant_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    intent: Optional[str] = Query(None),
    is_success: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.assistant_monitor", "read")),
):
    conds = [f"created_at >= NOW() - INTERVAL '{days} days'"]
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}
    if intent:
        conds.append("intent = :intent")
        params["intent"] = intent
    if is_success is not None:
        conds.append("is_success = :is_success")
        params["is_success"] = is_success
    where = " AND ".join(conds)
    total = (await db.execute(text(f"SELECT COUNT(*) FROM assistant_run WHERE {where}"))).scalar()
    rows = (await db.execute(text(
        f"SELECT id, trace_id, session_id, user_id, user_message, intent, tools_called, "
        f"tool_rounds, total_tokens, duration_ms, is_success, error_message, created_at "
        f"FROM assistant_run WHERE {where} ORDER BY id DESC LIMIT :limit OFFSET :offset"
    ), params)).mappings().all()
    return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


@router.get("/config", response_model=ResponseModel[dict])
async def get_assistant_config(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.assistant_config", "read")),
):
    from app.services.assistant.agent import SYSTEM_PROMPT, INTENT_RECOGNITION_PROMPT
    from app.core.config import get_settings

    config = await get_scope_config(db, ASSISTANT_SCOPE)
    config["system_prompt"] = config["system_prompt"] or SYSTEM_PROMPT
    config["intent_prompt"] = config["intent_prompt"] or INTENT_RECOGNITION_PROMPT
    config["model_name"] = config["model_name"] or get_settings().AI_OPENAI_MODEL
    disabled = set(config.get("disabled_tools") or [])
    return {
        "version": await get_scope_version(db, ASSISTANT_SCOPE),
        "config": config,
        "tools": [
            {
                "name": t.name,
                "display_name": t.display_name or t.name,
                "description": t.description,
                "disabled": t.name in disabled,
            }
            for t in get_all_tools()
        ],
        "defs": {k: {"label": d.label, "description": d.description} for k, d in SCOPE_DEFS[ASSISTANT_SCOPE].items()},
    }


@router.put("/config", response_model=ResponseModel[dict])
async def update_assistant_config(
    body: AssistantConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.assistant_config", "update")),
):
    operator = getattr(current_user, "username", None) or str(
        getattr(current_user, "user_id", "") or getattr(current_user, "id", ""))
    try:
        version = await save_scope_config(db, ASSISTANT_SCOPE, body.config, operator)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if body.config.get("disabled_tools") is not None:
        known = {t.name for t in get_all_tools()}
        if known and known.issubset(set(body.config["disabled_tools"])):
            return {"version": version, "warning": "全部工具已禁用，助手将无法查询业务数据"}
    return {"version": version}
```

> 说明：HTTPException(400) 会被全局异常处理转成前端可读错误；若仓库对 ValidationError 有统一信封处理，与 DataSupply 保存端点行为保持一致即可（执行时对照 `basicdata/data_supply.py` 的写法微调）。

文件：`backend/app/api/v1/system/__init__.py` 先改为（execution_agent 行在 Task 3.2 再加）：

```python
from app.api.v1.system.backups import router as backups_router
from app.api.v1.system.ai_assistant import router as ai_assistant_router

__all__ = ["backups_router", "ai_assistant_router"]
```

文件：`backend/app/api/v1/__init__.py` — 备份挂载行（约 105 行）后加：

```python
api_router.include_router(system.ai_assistant_router, prefix="/system/ai-assistant", tags=["系统管理-智能助手"])
```

（`/system/execution-agent` 挂载行在 Task 3.2 随路由文件一起加。）

验证：

```bash
cd backend && python -c "from app.api.v1.system import ai_assistant_router; print('ok')"
```

commit: `feat(ai-agents): 智能助手管理端点（stats/runs/config）`

---

## 阶段 3 · agent 侧后端

### Task 3.1 — 对外配置拉取端点 `agent.config`

文件：`backend/app/api/v1/external/endpoints/agent_config.py`（新建，完整内容）：

```python
"""执行面智能体配置拉取对外接口（endpoint_code: agent.config）

agent 启动/自重启时经 HMAC 拉取 DB 配置（scope=execution_agent），空值不下发（agent 继续用 env）。
签名串 = timestamp + app_key + endpoint_code + query_string（GET 无查询参数时 query_string 为空串）。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.basicdata.data_supply import DataSupplyApiKey
from app.schemas.common import ResponseModel
from app.services.ai_config import get_agent_external_config

from ..deps import external_auth
from ..log_wrap import log_external_call
from ..registry import register_external

router = APIRouter(prefix="/agent", tags=["智能体管理"])


@router.get("/config", response_model=ResponseModel[dict],
            summary="执行面智能体配置", description="endpoint_code: agent.config")
@register_external(
    "agent.config", "执行面智能体配置", method="GET", path="/agent/config",
    description="agent 启动/自重启时拉取运行时配置（非空 DB 值覆盖 env），附配置版本号",
    tags=["智能体管理"],
)
@log_external_call("agent.config")
async def agent_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("agent.config")),
):
    return await get_agent_external_config(db)
```

文件：`backend/app/api/v1/external/endpoints/__init__.py` — 末尾加：

```python
from . import agent_config  # noqa: F401
```

文件：`backend/app/api/v1/external/routes.py` — import 列表（`.endpoints` 的 from-import）加 `agent_config`，装配元组 `reasoning.router,` 后加 `agent_config.router,`。

验证：

```bash
cd backend && python -c "
from app.api.v1.external.routes import external_router
codes = {getattr(r, 'path', '') for r in external_router.routes}
assert '/agent/config' in codes or any('agent' in str(getattr(r,'path','')) for r in external_router.routes)
print('ok')"
```

（`check_registry_matches_router` 在 import 时执行，通过即代表注册表与路由一致。）

commit: `feat(ai-agents): 对外 agent.config 配置拉取端点（HMAC）`

### Task 3.2 — 管理端点 `/api/v1/system/execution-agent/*`

文件：`backend/app/api/v1/system/execution_agent.py`（新建，完整内容）：

```python
"""系统管理 — 执行面智能体管理端点（状态代理 / 配置 / 远程自重启，设计文档 2026-10-15）"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.schemas.common import ResponseModel
from app.services.ai_config import EXECUTION_AGENT_SCOPE, get_scope_config, get_scope_version, save_scope_config

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentConfigIn(BaseModel):
    config: dict


def _admin_headers() -> dict:
    return {"x-admin-token": get_settings().AGENT_ADMIN_TOKEN}


async def _call_agent(path: str, *, timeout: float = 10.0, method: str = "GET") -> dict:
    base = get_settings().EXECUTION_AGENT_BASE_URL.rstrip("/")
    if not base:
        return {"online": False, "reason": "EXECUTION_AGENT_BASE_URL 未配置"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, f"{base}{path}", headers=_admin_headers())
        if resp.status_code == 401:
            return {"online": False, "reason": "admin token 不匹配"}
        resp.raise_for_status()
        return {"online": True, **resp.json()}
    except httpx.HTTPError as e:
        return {"online": False, "reason": f"agent 不可达: {e.__class__.__name__}"}


@router.get("/status", response_model=ResponseModel[dict])
async def agent_status(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    agent = await _call_agent("/admin/status")
    recent = (await db.execute(text(
        "SELECT task_id, task_type, status, llm_called, error_code, duration_ms, created_at "
        "FROM reasoning_task ORDER BY id DESC LIMIT 10"
    ))).mappings().all()
    return {
        "agent": agent,
        "db_version": await get_scope_version(db, EXECUTION_AGENT_SCOPE),
        "config_pending_restart": (
            agent.get("online") and agent.get("configVersion") is not None
            and int(agent["configVersion"]) != await get_scope_version(db, EXECUTION_AGENT_SCOPE)
        ),
        "recent_reasoning_tasks": [dict(r) for r in recent],
    }


@router.get("/config", response_model=ResponseModel[dict])
async def get_agent_config(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "read")),
):
    from app.services.ai_config import SCOPE_DEFS
    return {
        "version": await get_scope_version(db, EXECUTION_AGENT_SCOPE),
        "config": await get_scope_config(db, EXECUTION_AGENT_SCOPE),
        "defs": {k: {"label": d.label, "description": d.description} for k, d in SCOPE_DEFS[EXECUTION_AGENT_SCOPE].items()},
    }


@router.put("/config", response_model=ResponseModel[dict])
async def update_agent_config(
    body: AgentConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.execution_agent", "update")),
):
    operator = getattr(current_user, "username", None) or str(
        getattr(current_user, "user_id", "") or getattr(current_user, "id", ""))
    try:
        version = await save_scope_config(db, EXECUTION_AGENT_SCOPE, body.config, operator)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"version": version, "message": "已保存；agent 重启后生效"}


@router.post("/restart", response_model=ResponseModel[dict])
async def restart_agent(
    current_user=Depends(PermissionChecker("ai.execution_agent", "update")),
):
    result = await _call_agent("/admin/restart", method="POST", timeout=5.0)
    if not result.get("online"):
        raise HTTPException(status_code=503, detail=f"无法重启：{result.get('reason')}")
    return {"message": "重启指令已下发，容器 restart 策略将自动拉起"}
```

随后完成挂载：`backend/app/api/v1/system/__init__.py` 补 `from app.api.v1.system.execution_agent import router as execution_agent_router` 与 `__all__` 项；`backend/app/api/v1/__init__.py` 在 ai-assistant 挂载行后加：

```python
api_router.include_router(system.execution_agent_router, prefix="/system/execution-agent", tags=["系统管理-执行面智能体"])
```

验证：

```bash
cd backend && python -c "
from app.api.v1 import api_router
paths = [getattr(r, 'path', '') for r in api_router.routes]
assert any('execution-agent' in p for p in paths), paths[:5]
print('ok')"
```

commit: `feat(ai-agents): 执行面智能体管理端点（status/config/restart）`

### Task 3.3 — 后端测试

文件：`backend/tests/conftest.py` — 三处小改：

1. `EXTERNAL_REASONING_KEY = ...` 行后加：

```python
EXTERNAL_AGENT_KEY = {"app_key": "ak_pytest_agent", "app_secret": "sk_pytest_agent"}
```

2. `external_keys` fixture 的 INSERT 语句 VALUES 增加一行（reasoning 行后）：

```sql
                ('pytest-agent', 'ak_pytest_agent', TRUE,
                 '["agent.config"]', 0, :gak, :gas, NULL, 'pytest')
```

params 增加：

```python
            "gak": EXTERNAL_AGENT_KEY["app_key"], "gas": EXTERNAL_AGENT_KEY["app_secret"],
```

yield 增加：

```python
        "agent": EXTERNAL_AGENT_KEY,
```

3. `client` fixture 的 TRUNCATE 列表末尾追加 `ai_agent_config, assistant_run`（与现有列表逗号衔接，`backup_record` 前后均可，保持一行内）。

文件：`backend/tests/unit/test_ai_config.py`（新建，完整内容）：

```python
"""ai_config 纯函数单测：类型校正 / 白名单 / 提示词渲染"""

import pytest

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
```

文件：`backend/tests/integration/test_ai_agent_management_api.py`（新建，完整内容）：

```python
"""智能体管理台集成测试：配置白名单/版本 bump/统计聚合/agent.config HMAC 拉取"""

import time

from sqlalchemy import text

from tests._common_external import build_headers, generate_signature
from tests.conftest import login


async def test_assistant_config_whitelist_and_version(client):
    headers = await login(client, "admin")

    r = await client.put("/api/v1/system/ai-assistant/config",
                         json={"config": {"hack_key": 1}}, headers=headers)
    assert r.json().get("code") != 0

    r = await client.put("/api/v1/system/ai-assistant/config",
                         json={"config": {"temperature": 0.5, "disabled_tools": ["search_users"]}},
                         headers=headers)
    body = r.json()
    assert body["code"] == 0
    v1 = body["data"]["version"]
    assert v1 >= 1

    r = await client.put("/api/v1/system/ai-assistant/config",
                         json={"config": {"temperature": 0.7}}, headers=headers)
    assert r.json()["data"]["version"] == v1 + 1

    r = await client.get("/api/v1/system/ai-assistant/config", headers=headers)
    config = r.json()["data"]["config"]
    assert config["temperature"] == 0.7
    tools = {t["name"]: t for t in r.json()["data"]["tools"]}
    assert tools["search_users"]["disabled"] is True


async def test_assistant_stats_and_runs(client, db):
    headers = await login(client, "admin")

    await db.execute(text(
        "INSERT INTO assistant_run (trace_id, session_id, user_id, user_message, intent, "
        "tools_called, tool_rounds, total_tokens, duration_ms, is_success, created_at) VALUES "
        "('t1', 's1', 'admin', '查订单', 'agent', '[\"search_orders\"]'::jsonb, 1, 100, 1500.0, TRUE, NOW()), "
        "('t2', 's2', 'admin', '你好', 'general_chat', NULL, 0, 20, 300.0, FALSE, NOW())"
    ))
    await db.commit()

    r = await client.get("/api/v1/system/ai-assistant/stats?days=7", headers=headers)
    data = r.json()["data"]
    assert data["total"] == 2 and data["success"] == 1 and data["total_tokens"] == 120
    assert data["top_tools"][0]["tool"] == "search_orders"

    r = await client.get("/api/v1/system/ai-assistant/runs?days=7", headers=headers)
    assert r.json()["data"]["total"] == 2
    r = await client.get("/api/v1/system/ai-assistant/runs?days=7&is_success=false", headers=headers)
    assert r.json()["data"]["total"] == 1


async def test_execution_agent_config_and_external_fetch(ext_client, client):
    headers = await login(client, "admin")

    r = await client.put("/api/v1/system/execution-agent/config",
                         json={"config": {"query_timeout_ms": 20000, "log_level": "debug"}}, headers=headers)
    assert r.json()["code"] == 0

    key = {"app_key": "ak_pytest_agent", "app_secret": "sk_pytest_agent"}
    ts = int(time.time())
    _, sig = generate_signature(ts, key["app_key"], key["app_secret"], "agent.config", "")
    r = await ext_client.get("/api/v1/external/agent/config",
                             headers=build_headers(key["app_key"], sig, ts))
    data = r.json()["data"]
    assert data["version"] >= 1
    assert data["config"]["query_timeout_ms"] == 20000
    assert data["config"]["log_level"] == "debug"
    # 空值不下发（agent 继续用 env）
    assert "agent_name" not in data["config"]


async def test_execution_agent_status_offline(client):
    headers = await login(client, "admin")
    r = await client.get("/api/v1/system/execution-agent/status", headers=headers)
    assert r.json()["code"] == 0
    assert r.json()["data"]["agent"]["online"] is False
```

> 注意：`ext_client` fixture 先清 `data_supply_api_key` 表并种 key，`client` fixture 又会 TRUNCATE `ai_agent_config` —— `test_execution_agent_config_and_external_fetch` 同时用两个 fixture 时顺序由声明顺序决定；若 TRUNCATE 冲突导致 flaky，改为在该用例内先 PUT 再 GET external（如上已如此）。执行时若 `assistant_run` 落库受外键/时区影响，先 `python -m pytest tests/integration/test_ai_agent_management_api.py -v` 单跑排查。

验证：

```bash
cd backend && python -m pytest tests/unit/test_ai_config.py tests/integration/test_ai_agent_management_api.py -v
python -m pytest -x -q   # 全量回归（改了 conftest，必须全跑）
```

commit: `test(ai-agents): 配置白名单/版本/统计/agent.config 集成与单元测试`

---

## 阶段 4 · Node agent（aeos-execution-agent）

### Task 4.1 — config.js 增 adminToken；remote-config 拉取模块

文件：`aeos-execution-agent/src/config.js` — `const config = {...}` 对象内 `logLevel` 行后加：

```js
  // 管理台 admin 面令牌（backend 代理调 /admin/* 时携带；空=禁用 admin 面）
  adminToken: process.env.AGENT_ADMIN_TOKEN ?? fileVars.AGENT_ADMIN_TOKEN ?? "",
  // 远程配置版本（成功拉取 DB 配置后写入；/admin/status 上报）
  configVersion: 0,
```

文件：`aeos-execution-agent/src/lib/remote-config.js`（新建，完整内容）：

```js
"use strict";

const config = require("../config");
const { log, signedGet } = require("./http-client");

/** DB 配置键 → config 属性映射（仅非空值覆盖 env） */
const KEY_TO_PROP = {
  agent_name: "agentName",
  ws_url: "wsUrl",
  agent_id: "agentId",
  query_timeout_ms: "queryTimeoutMs",
  reasoning_timeout_ms: "reasoningTimeoutMs",
  log_level: "logLevel",
};

async function applyRemoteConfig() {
  const payload = await signedGet("/external/agent/config", "agent.config", {});
  const remote = (payload && payload.config) || {};
  const applied = [];
  for (const [key, prop] of Object.entries(KEY_TO_PROP)) {
    const value = remote[key];
    if (value === undefined || value === null || value === "") continue;
    if (String(config[prop]) === String(value)) continue;
    config[prop] = prop.endsWith("_ms") ? Number(value) : value;
    applied.push(key);
  }
  config.configVersion = (payload && payload.version) || 0;
  log("info", "remote_config_applied", {
    version: config.configVersion,
    keys: applied,
    agentId: config.agentId,
    wsUrl: config.wsUrl,
  });
}

/** 启动即拉一次；失败用 env 值继续，每 60s 重试直到首次成功（只成功一次即停） */
function applyRemoteConfigWithRetry() {
  const timer = setInterval(async () => {
    try {
      await applyRemoteConfig();
      clearInterval(timer);
    } catch (e) {
      log("warn", "remote_config_retry_failed", { message: e.message });
    }
  }, 60_000);
  timer.unref();
  return applyRemoteConfig().catch((e) => {
    log("warn", "remote_config_failed", { message: e.message });
  });
}

module.exports = { applyRemoteConfig, applyRemoteConfigWithRetry };
```

> `wsUrl`/`agentId` 覆盖只在新连接/重新 register 时生效（protocol.js 均为调用时读取），拉取发生在 `connection.start()` 之前，首次连接即用新值。

commit: `feat(execution-agent): 运行时配置拉取（HMAC agent.config，env 兜底）`

### Task 4.2 — index.js：admin 面 + 0.0.0.0 监听 + 启动拉配置

文件：`aeos-execution-agent/src/index.js` 改造（完整替换后三个函数区）：

1. 顶部 require 加：

```js
const { applyRemoteConfigWithRetry } = require("./lib/remote-config");
```

2. `startHealthServer` 整体替换为：

```js
function startHealthServer(connection) {
  if (config.healthCheckPort <= 0) return null;
  const server = http.createServer((req, res) => {
    const pathname = req.url ? req.url.split("?")[0] : "";
    const send = (status, body) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(body));
    };
    if (pathname === "/healthz") {
      const ok = connection.isRegistered();
      send(ok ? 200 : 503, { status: ok ? "ok" : "not_registered" });
    } else if (pathname.startsWith("/admin/")) {
      if (!config.adminToken) return send(503, { status: "admin_disabled" });
      const token = req.headers["x-admin-token"];
      if (token !== config.adminToken) return send(401, { status: "unauthorized" });
      if (pathname === "/admin/status" && req.method === "GET") {
        send(200, {
          registered: connection.isRegistered(),
          currentRunId: connection.activeRun ? connection.activeRun.runId : null,
          configVersion: config.configVersion,
          uptimeS: Math.floor(process.uptime()),
          agentId: config.agentId,
          capabilities: handlers.capabilities.map((c) => c.name),
        });
      } else if (pathname === "/admin/restart" && req.method === "POST") {
        send(200, { status: "restarting" });
        log("info", "admin_restart_requested", {});
        setTimeout(() => process.exit(0), 150);
      } else {
        send(404, { status: "not_found" });
      }
    } else {
      send(404, { status: "not_found" });
    }
  });
  server.on("error", (err) => log("error", "health_server_error", { message: err.message }));
  // 0.0.0.0：backend 容器经 compose 网络访问（此前仅 127.0.0.1 本机可达）
  server.listen(config.healthCheckPort, "0.0.0.0");
  log("info", "health_server_listening", { port: config.healthCheckPort, bind: "0.0.0.0" });
  return server;
}
```

3. `main()` 中 `const connection = new HubConnection(handlers);` 之前插入：

```js
  // DB 运行时配置：启动即拉一次（失败用 env 继续 + 后台重试），须在建连前完成
  await applyRemoteConfigWithRetry();
```

`main` 签名改 `async function main()`（末尾调用不变）。

> 说明：`connection.activeRun` 属性已在 protocol.js 存在（构造器 `this.activeRun = null`）；若 runId 字段名与实际不符，以 protocol.js 内 activeRun 赋值代码为准对齐（执行时核对 `dispatch` 处理段）。

验证：

```bash
cd aeos-execution-agent && node --check src/config.js && node --check src/lib/remote-config.js && node --check src/index.js
```

冒烟（另开终端）：

```bash
cd aeos-execution-agent && cp .env.example .env.local  # 填本机可用的 CONTROL_PLATFORM_* 指向开发后端
AGENT_ADMIN_TOKEN=dev-token npm start
# 另一终端：
curl http://127.0.0.1:8790/healthz
curl -H "x-admin-token: dev-token" http://127.0.0.1:8790/admin/status
curl -X POST -H "x-admin-token: dev-token" http://127.0.0.1:8790/admin/restart   # 进程退出码 0
curl -H "x-admin-token: wrong" http://127.0.0.1:8790/admin/status                 # 401
```

commit: `feat(execution-agent): admin 面（status/restart + token 校验）与 0.0.0.0 监听`

### Task 4.3 — 模板与文档

文件：`aeos-execution-agent/.env.example` — `LOG_LEVEL=info` 行后加：

```env
# 管理台 admin 面令牌（backend EXECUTION 管理页经它调用 /admin/status|restart；空=禁用 admin 面）
AGENT_ADMIN_TOKEN=change-me
```

文件：`docker-compose.yml`（仓库根）— `aeos-execution-agent` 服务 `environment:` 列表末尾（`CONTROL_PLATFORM_REASONING_TIMEOUT_MS` 行后）加：

```yaml
      AGENT_ADMIN_TOKEN: ${AGENT_ADMIN_TOKEN:-}
```

文件：`aeos-execution-agent/docker-compose.yml` — 同样补 `AGENT_ADMIN_TOKEN: ${AGENT_ADMIN_TOKEN:-}`。

文件：`aeos-execution-agent/README.md` — 「接入步骤」第 1 步勾选清单补 `agent.config`；「运行」前补一条：

```markdown
5. **管理台对接**：根 `.env` 同步配 `AGENT_ADMIN_TOKEN`（与 backend 侧一致）；
   backend 配 `EXECUTION_AGENT_BASE_URL=http://aeos-execution-agent:8790` 后，
   系统管理「执行面智能体」页可看状态/改配置（重启后生效）/远程重启。
```

验证：

```bash
docker compose config --quiet 2>$null; echo compose-ok
```

（在仓库根执行；或肉眼核对 YAML 缩进。）

commit: `feat(execution-agent): .env/compose 模板补 AGENT_ADMIN_TOKEN，README 管理台对接说明`

---

## 阶段 5 · 前端

### Task 5.1 — 路由与菜单

文件：`frontend/src/router/contentRoutes.tsx`：
1. import 区（`import Backup from '../pages/SystemCenter/Backup'` 行后）加：

```tsx
import AssistantManagement from '../pages/SystemCenter/AssistantManagement'
import ExecutionAgentManagement from '../pages/SystemCenter/ExecutionAgentManagement'
```

2. 路由注册（`/backups` 路由行附近）加：

```tsx
        <Route path="/ai-assistant" element={<AssistantManagement/>} key="ai-assistant"/>
        <Route path="/execution-agent" element={<ExecutionAgentManagement/>} key="execution-agent"/>
```

文件：`frontend/src/layouts/MainLayout.tsx`：
1. 图标 import 行补 `RobotOutlined`（@ant-design/icons 导入列表内）。
2. fallback 菜单（`{ key: '/backups', ... }` 行后）加：

```tsx
      { key: '/ai-assistant', icon: <RobotOutlined />, label: '智能助手管理', permission: 'ai.assistant_monitor' },
      { key: '/execution-agent', icon: <ApiOutlined />, label: '执行面智能体', permission: 'ai.execution_agent' },
```

3. `pathToGroupKey`（`'/backups': 'basicdata-center',` 行后）加：

```tsx
  '/ai-assistant': 'basicdata-center',
  '/execution-agent': 'basicdata-center',
```

4. `pathToPermission`（`'/backups': 'backup',` 行后）加：

```tsx
  '/ai-assistant': 'ai.assistant_monitor',
  '/execution-agent': 'ai.execution_agent',
```

验证：留到 Task 5.4 一起 `npm run build`。

commit: `feat(ai-agents): 智能助手/执行面智能体路由与菜单接入`

### Task 5.2 — 智能助手管理页

文件：`frontend/src/pages/SystemCenter/AssistantManagement/index.tsx`（新建，完整内容）：

```tsx
import { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Col, Form, Input, InputNumber, Modal, Row, Spin, Switch,
  Table, Tabs, Tag, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Column } from '@ant-design/charts'
import { api } from '../../../services/api'
import { useAuthStore } from '../../../store/auth'

interface ToolItem { name: string; display_name: string; description: string; disabled: boolean }
interface RunRow {
  id: number; trace_id: string; user_id: string | null; user_message: string | null
  intent: string | null; tools_called: string[] | null; tool_rounds: number | null
  total_tokens: number | null; duration_ms: number | null; is_success: boolean
  error_message: string | null; created_at: string
}
interface StatsData {
  total: number; success: number; success_rate: number | null; avg_duration_ms: number
  total_tokens: number; active_users: number
  trend: { day: string; total: number; ok: number }[]
  top_tools: { tool: string; hits: number }[]
}

const INTENT_LABELS: Record<string, string> = {
  query_data: '查数据', analyze_history: '析历史', general_chat: '闲聊', agent: '工具链', unknown: '未知',
}

function OverviewTab({ days }: { days: number }) {
  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get('/system/ai-assistant/stats', { params: { days } })
      setStats(res.data.data)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => { refresh() }, [refresh])
  if (loading || !stats) return <Spin/>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={16}>
        {[
          ['总对话', stats.total], ['成功率', stats.success_rate == null ? '-' : `${(stats.success_rate * 100).toFixed(1)}%`],
          ['平均耗时', `${(stats.avg_duration_ms / 1000).toFixed(1)}s`], ['累计 token', stats.total_tokens],
          ['活跃用户', stats.active_users],
        ].map(([label, value]) => (
          <Col key={String(label)} span={4}><Card size="small"><div style={{ opacity: 0.65 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 600 }}>{value}</div></Card></Col>
        ))}
      </Row>
      <Card size="small" title={`每日趋势（近 ${days} 天）`}>
        <Column height={220} data={stats.trend} xField="day" yField="total"
                 colorField="#1677ff" label={{ text: (d: any) => d.total }}/>
      </Card>
      <Card size="small" title="工具命中 Top10">
        <Column height={220} data={stats.top_tools} xField="tool" yField="hits"
                 colorField="#52c41a" label={{ text: (d: any) => d.hits }}/>
      </Card>
    </div>
  )
}

function RunsTab({ days }: { days: number }) {
  const [rows, setRows] = useState<RunRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<{ trace_id: string; records: any[] } | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get('/system/ai-assistant/runs', { params: { days, page, page_size: pageSize } })
      setRows(res.data.data.items)
      setTotal(res.data.data.total)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [days, page, pageSize])

  useEffect(() => { refresh() }, [refresh])

  const openDetail = async (traceId: string) => {
    try {
      const res = await api.get(`/assistant/logs/${traceId}`)
      const data = res.data.data
      if (!data) return message.error('未找到该 trace 的文件日志')
      setDetail({ trace_id: traceId, records: data.records })
    } catch (e: any) {
      message.error(String(e?.message || e))
    }
  }

  const columns: ColumnsType<RunRow> = [
    { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => new Date(v).toLocaleString() },
    { title: '用户', dataIndex: 'user_id', width: 90 },
    { title: '意图', dataIndex: 'intent', width: 90, render: (v: string) => INTENT_LABELS[v] || v || '-' },
    { title: '提问', dataIndex: 'user_message', ellipsis: true },
    {
      title: '工具', dataIndex: 'tools_called', width: 200,
      render: (v: string[]) => v?.length ? v.map((t) => <Tag key={t} style={{ marginInlineEnd: 4 }}>{t}</Tag>) : '-',
    },
    { title: '轮数', dataIndex: 'tool_rounds', width: 60, align: 'center' },
    { title: 'token', dataIndex: 'total_tokens', width: 80, align: 'right' },
    { title: '耗时', dataIndex: 'duration_ms', width: 80, align: 'right', render: (v: number) => v != null ? `${(v / 1000).toFixed(1)}s` : '-' },
    {
      title: '状态', dataIndex: 'is_success', width: 80,
      render: (v: boolean, row) => v ? <Tag color="success">成功</Tag> :
        <Tag color="error" title={row.error_message || ''}>失败</Tag>,
    },
    { title: '', width: 70, render: (_v, row) => <a onClick={() => openDetail(row.trace_id)}>trace</a> },
  ]

  return (
    <>
      <Table rowKey="id" size="small" columns={columns} dataSource={rows} loading={loading}
             pagination={{ current: page, pageSize, total, showSizeChanger: true,
                           onChange: (p, s) => { setPage(p); setPageSize(s) } }}/>
      <Modal open={!!detail} title={`Trace 详情 ${detail?.trace_id || ''}`} footer={null}
             width={860} onCancel={() => setDetail(null)} destroyOnClose>
        <div style={{ maxHeight: 480, overflow: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
          {(detail?.records || []).map((r: any, i: number) => (
            <pre key={i} style={{ margin: 0, padding: 6, borderBottom: '1px solid #f0f0f0' }}>
              {JSON.stringify(r, null, 2)}
            </pre>
          ))}
        </div>
      </Modal>
    </>
  )
}

文件：`frontend/src/pages/SystemCenter/AssistantManagement/index.tsx`（新建，完整内容；`OverviewTab` / `RunsTab` 用上文代码，`ConfigTab` 与默认导出如下）：

```tsx
function ConfigTab() {
  const [form] = Form.useForm()
  const [tools, setTools] = useState<ToolItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get('/system/ai-assistant/config')
      const d = res.data.data
      form.setFieldsValue(d.config)
      setTools(d.tools)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [form])

  useEffect(() => { refresh() }, [refresh])

  const save = async () => {
    const values = await form.validateFields()
    const disabled = tools.filter((t) => t.disabled).map((t) => t.name)
    setSaving(true)
    try {
      const res = await api.put('/system/ai-assistant/config', {
        config: { ...values, disabled_tools: disabled },
      })
      message.success(`已保存（版本 v${res.data.data.version}，即时生效）`)
      if (res.data.data.warning) message.warning(res.data.data.warning)
      refresh()
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Spin spinning={loading}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 960 }}>
        <Alert type="info" showIcon
               message={'系统提示词支持 {{TOOLS}} 占位符：构建对话时自动注入当前启用工具清单；两段提示词留空即恢复内置默认。'}/>
        <Card size="small" title="提示词">
          <Form form={form} layout="vertical">
            <Form.Item name="system_prompt" label="系统提示词">
              <Input.TextArea rows={12} showCount={{ show: false }}/>
            </Form.Item>
            <Form.Item name="intent_prompt" label="意图识别提示词">
              <Input.TextArea rows={8}/>
            </Form.Item>
          </Form>
        </Card>
        <Card size="small" title="模型参数">
          <Form form={form} layout="vertical">
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="model_name" label="模型名（留空用 .env 默认）">
                  <Input allowClear placeholder="如 glm-4.6 / gpt-4o-mini"/>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="temperature" label="温度" initialValue={0.1}>
                  <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }}/>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="max_tokens" label="最大输出 token" initialValue={4096}>
                  <InputNumber min={256} max={32768} step={256} style={{ width: '100%' }}/>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="max_tool_rounds" label="工具循环轮数上限" initialValue={5}>
                  <InputNumber min={1} max={20} style={{ width: '100%' }}/>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="tool_execute_timeout" label="工具执行超时（秒）" initialValue={30}>
                  <InputNumber min={5} max={300} style={{ width: '100%' }}/>
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </Card>
        <Card size="small" title={`工具启停（${tools.filter((t) => !t.disabled).length}/${tools.length} 启用）`}>
          <Table rowKey="name" size="small" pagination={false}
                 dataSource={tools}
                 columns={[
                   { title: '工具', dataIndex: 'display_name', width: 220 },
                   { title: '说明', dataIndex: 'description', ellipsis: true },
                   {
                     title: '启用', dataIndex: 'disabled', width: 90,
                     render: (v: boolean, row: ToolItem) => (
                       <Switch checked={!v} onChange={(checked) => {
                         setTools((prev) => prev.map((t) =>
                           t.name === row.name ? { ...t, disabled: !checked } : t))
                       }}/>
                     ),
                   },
                 ]}/>
        </Card>
        <div>
          <Button type="primary" loading={saving} onClick={save}>保存配置</Button>
        </div>
      </div>
    </Spin>
  )
}
```

页面默认导出：

```tsx
export default function AssistantManagement() {
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (r: string, a: string) => boolean
  const canConfig = hasPermission('ai.assistant_config', 'update')
  const [days] = useState(30)

  const tabs = [
    { key: 'overview', label: '概览', children: <OverviewTab days={days}/> },
    { key: 'runs', label: '运行记录', children: <RunsTab days={days}/> },
  ]
  if (canConfig) tabs.push({ key: 'config', label: '配置', children: <ConfigTab/> })

  return (
    <div style={{ padding: 16 }}>
      <Tabs defaultActiveKey="overview" items={tabs}/>
    </div>
  )
}
```

commit: `feat(ai-agents): 智能助手管理页（概览/运行记录/配置）`

### Task 5.3 — 执行面智能体管理页

文件：`frontend/src/pages/SystemCenter/ExecutionAgentManagement/index.tsx`（新建，完整内容）：

```tsx
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Badge, Button, Card, Col, Form, Input, InputNumber, Modal, Row, Select, Space,
  Spin, Table, Tag, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { api } from '../../../services/api'
import { useAuthStore } from '../../../store/auth'

interface AgentStatus {
  agent: { online: boolean; registered?: boolean; currentRunId?: string | null
           configVersion?: number; uptimeS?: number; agentId?: string; reason?: string
           capabilities?: string[] }
  db_version: number
  config_pending_restart: boolean
  recent_reasoning_tasks: {
    task_id: string; task_type: string | null; status: string; llm_called: number
    error_code: number | null; duration_ms: string | null; created_at: string
  }[]
}

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  running: { color: 'processing', label: '运行中' },
  succeeded: { color: 'success', label: '成功' },
  failed: { color: 'error', label: '失败' },
  cancelled: { color: 'default', label: '已取消' },
  timeout: { color: 'warning', label: '超时' },
}

export default function ExecutionAgentManagement() {
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (r: string, a: string) => boolean
  const canManage = hasPermission('ai.execution_agent', 'update')
  const [form] = Form.useForm()
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const pollRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await api.get('/system/execution-agent/status')
      setStatus(res.data.data)
    } catch (e: any) {
      message.error(String(e?.message || e))
    }
  }, [])

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      await refresh()
      const res = await api.get('/system/execution-agent/config')
      form.setFieldsValue(res.data.data.config)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [form, refresh])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => () => { if (pollRef.current) window.clearInterval(pollRef.current) }, [])

  const save = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const res = await api.put('/system/execution-agent/config', {
        config: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v ?? ''])),
      })
      message.success(`已保存 v${res.data.data.version}，agent 重启后生效`)
      refresh()
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setSaving(false)
    }
  }

  const restart = () => {
    Modal.confirm({
      title: '远程重启执行面智能体？',
      content: '重启期间 Hub 派单会被忙拒/重连，约持续数秒。',
      okText: '重启', okButtonProps: { danger: true },
      onOk: async () => {
        setRestarting(true)
        try {
          await api.post('/system/execution-agent/restart')
          message.success('重启指令已下发')
          let ticks = 0
          if (pollRef.current) window.clearInterval(pollRef.current)
          pollRef.current = window.setInterval(async () => {
            ticks += 1
            await refresh()
            if (status?.agent.online || ticks > 20) {
              window.clearInterval(pollRef.current!)
              pollRef.current = null
              setRestarting(false)
              if (status?.agent.online) message.success('agent 已恢复')
            }
          }, 3000)
        } catch (e: any) {
          setRestarting(false)
          message.error(String(e?.message || e))
        }
      },
    })
  }

  if (loading && !status) return <Spin style={{ padding: 48 }}/>
  const agent = status?.agent
  const pending = status?.config_pending_restart

  const taskColumns: ColumnsType<AgentStatus['recent_reasoning_tasks'][number]> = [
    { title: 'runId / task_id', dataIndex: 'task_id', width: 200, ellipsis: true },
    { title: '类型', dataIndex: 'task_type', width: 180, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => <Tag color={STATUS_TAG[v]?.color || 'default'}>{STATUS_TAG[v]?.label || v}</Tag>,
    },
    { title: '真实 LLM', dataIndex: 'llm_called', width: 90, render: (v: number) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    { title: '耗时', dataIndex: 'duration_ms', width: 90, align: 'right', render: (v: string | null) => v ? `${(Number(v) / 1000).toFixed(1)}s` : '-' },
    { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => new Date(v).toLocaleString() },
  ]

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card size="small" title="状态">
        <Row gutter={16}>
          <Col span={4}>
            <Badge status={agent?.online ? 'success' : 'error'}
                   text={agent?.online ? (agent.registered ? '已注册在线' : '在线未注册') : '不可达'}/>
          </Col>
          <Col span={4}>AgentID：{agent?.agentId || '-'}</Col>
          <Col span={4}>当前 run：{agent?.currentRunId || '-'}</Col>
          <Col span={4}>uptime：{agent?.uptimeS != null ? `${Math.floor(agent.uptimeS / 60)} 分钟` : '-'}</Col>
          <Col span={4}>
            配置版本：
            <Tag color={pending ? 'orange' : 'green'}>
              v{agent?.configVersion ?? '-'}{pending ? ` ≠ v${status?.db_version}，需重启` : ''}
            </Tag>
          </Col>
          {canManage && (
            <Col span={2} offset={0}>
              <Button danger loading={restarting} onClick={restart}>远程重启</Button>
            </Col>
          )}
        </Row>
        {!agent?.online && <div style={{ marginTop: 8, opacity: 0.65, fontSize: 12 }}>{agent?.reason || ''}</div>}
      </Card>

      <Card size="small" title="配置（保存后 agent 重启生效；留空项沿用 .env）">
        <Form form={form} layout="vertical" style={{ maxWidth: 860 }}>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="agent_name" label="注册显示名"><Input allowClear placeholder="留空用 env"/></Form.Item></Col>
            <Col span={12}><Form.Item name="agent_id" label="Agent ID"><Input allowClear placeholder="留空用 env"/></Form.Item></Col>
            <Col span={12}><Form.Item name="ws_url" label="Hub WebSocket 地址"><Input allowClear placeholder="留空用 env"/></Form.Item></Col>
            <Col span={4}><Form.Item name="query_timeout_ms" label="查询超时(ms)"><InputNumber min={1000} max={120000} step={1000} style={{ width: '100%' }}/></Form.Item></Col>
            <Col span={4}><Form.Item name="reasoning_timeout_ms" label="推理超时(ms)"><InputNumber min={10000} max={600000} step={10000} style={{ width: '100%' }}/></Form.Item></Col>
            <Col span={4}>
              <Form.Item name="log_level" label="日志级别">
                <Select options={['debug', 'info', 'warn', 'error'].map((v) => ({ value: v, label: v }))}/>
              </Form.Item>
            </Col>
          </Row>
        </Form>
        {canManage && (
          <Space>
            <Button type="primary" loading={saving} onClick={save}>保存配置</Button>
            {pending && <Button danger onClick={restart}>配置未生效，立即重启</Button>}
          </Space>
        )}
      </Card>

      <Card size="small" title="最近推理任务（reasoning_task 审计）">
        <Table rowKey="task_id" size="small" columns={taskColumns}
               dataSource={status?.recent_reasoning_tasks || []} pagination={false}/>
      </Card>
    </div>
  )
}
```

commit: `feat(ai-agents): 执行面智能体管理页（状态/配置/重启/推理审计）`

### Task 5.4 — 前端构建验证

```bash
cd frontend && npm run build
```

预期：tsc -b 与 vite build 均零错误；若报未使用 import，按 TS 提示清理。

commit（如有修复）: `fix(ai-agents): 前端构建问题修复`

---

## 阶段 6 · 端到端验证

### Task 6.1 — 后端全量回归

```bash
cd backend && python -m pytest -v
```

预期：既有套件 + 新增 3 个测试文件全绿。重点确认无 "Future attached to a different loop"（conftest 两行 loop_scope 未动即不会出现）。

### Task 6.2 — 端到端冒烟（开发环境）

1. `python init_database.py`（建 `ai_agent_config` / `assistant_run` 表；幂等）
2. `uvicorn app.main:app --reload --port 8000`
3. admin 登录 → 系统管理出现「智能助手管理」「执行面智能体」菜单
4. 配置页禁用一个工具 → 保存 → 顶栏 AI 搜索提问命中该工具的问题 → 回复提示工具被禁用；重新启用后恢复
5. 修改系统提示词加 `{{TOOLS}}` → 保存 → 对话正常（日志中 system 消息含工具清单）
6. agent 冒烟链（Task 4.2 的 curl 序列）+ 管理页「远程重启」按钮 → 状态由不可达 → 在线
7. `PUT /system/execution-agent/config` 后 `/admin/status` 的 configVersion 落后于 DB → 页面显示橙色「需重启」

### Task 6.3 — 部署注意（不在本计划内执行，仅记录）

- 生产 compose（`docker-compose-prod.yml`）需补 `aeos-execution-agent` 服务（含 `AGENT_ADMIN_TOKEN`）；backend `.env` 增 `EXECUTION_AGENT_BASE_URL` / `AGENT_ADMIN_TOKEN`
- agent 的数据供给 AppKey 需在「数据供给」页勾选新端点 `agent.config`

---

## 任务依赖图

```
1.1 → 1.2 → 1.3, 1.4（独立）
1.2 → 2.3 → 2.4 → 2.5 → 2.6 ┐
2.1, 2.2 → 2.3               ├→ 3.3 → 6.1
1.2, 1.4 → 3.1, 3.2 ─────────┘
3.1 → 4.1 → 4.2 → 4.3
1.3 → 5.1 → 5.2 → 5.3 → 5.4 → 6.2
```
