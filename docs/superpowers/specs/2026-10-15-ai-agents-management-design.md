# 中台智能助手与 aeos-execution-agent 前端管理台 · 设计文档

- 日期：2026-10-15
- 状态：已评审通过（方案 A：DB 配置中心 + agent 拉取）
- 范围：智能助手（工具启停 / 模型与提示词 / 用量统计 / 运行日志监控）+ 执行面智能体（配置可编辑 / 远程自重启）

## 1. 背景与现状

| 对象 | 后端现状 | 前端现状 |
|---|---|---|
| 中台智能助手 | `app/services/assistant/`：chat/SSE、14 个代码注册工具、提示词与模型参数硬编码（`agent.py` / `config.py` Settings）、运行日志落文件（`/api/v1/assistant/logs`） | 仅顶栏 AI 搜索入口 |
| aeos-execution-agent | Node sidecar（`aeos-execution-agent/`），反向 WS 连 AEOS Hub；配置全部来自 `.env`；healthz 仅监听 `127.0.0.1:8790`；推理任务审计在 `reasoning_task` 表 | 无 |

## 2. 方案选型

**方案 A（采纳）：DB 配置中心 + agent 拉取。** 配置存数据库，env 退化为默认/引导值；助手侧每请求读 DB 即时生效；agent 启动/自重启时经既有 HMAC 外部 API 拉取；敏感项不进 DB。

否决：
- 方案 B（通用配置中心抽象）：目前仅两个消费者，YAGNI，抽象与迁移成本高。
- 方案 C（前端壳 + 仍走 .env）：不满足「配置可编辑」需求。

远程重启机制：**agent 自重启**（agent 新增 token 保护的 `/admin/restart`，`process.exit(0)` 后靠容器 `restart: unless-stopped` 拉起）。否决 backend 挂 docker.sock 直控宿主（安全面大）。

## 3. 总体架构

```
┌─ 前端 SystemCenter ─────────────────────────────────────┐
│ /ai-assistant（智能助手管理）   /execution-agent（执行面智能体）│
└──────────────┬───────────────────────────┬──────────────┘
               │ JWT + ai.* 权限            │
┌─ backend ────▼───────────────────────────▼──────────────┐
│ /api/v1/system/ai-assistant/*   /api/v1/system/execution-agent/* │
│ 配置读写 → ai_agent_config 表（版本号 bump）                    │
│ 用量统计 ← assistant_run 表                                    │
│ agent 代理 ──HTTP──► agent /admin/*（x-admin-token 校验）      │
└──────────────┬────────────────────────────────────────────┘
               │ 启动/重启时 HMAC 拉配置（复用数据供给 AppKey 体系）
        ┌──────▼───────┐
        │ Node agent   │─ WS ─► AEOS Hub（不变）
        └──────────────┘
```

- 配置单点在 DB；backend 访问 agent 的地址来自新 Settings 项 `EXECUTION_AGENT_BASE_URL`（如 `http://aeos-execution-agent:8790`），留 env（引导配置，不进 DB）。
- 不进 DB 的敏感项：`appKey/appSecret`、`CONTROL_PLATFORM_BASE_URL`（拉配置的通道本身）、`EXECUTION_PLANE_TOKEN`、`AGENT_ADMIN_TOKEN`、AI provider API Key。

## 4. 数据模型（新表 ×2）

models 注册进 `app/models/__init__.py` → `create_all` 自建，无需 `migrate_columns`；seed 加在 `init_database.py`。

### 4.1 `ai_agent_config`

| 列 | 说明 |
|---|---|
| id | 主键 |
| scope | `assistant` \| `execution_agent` |
| config_key | 配置键 |
| config_value | text |
| value_type | `string` \| `int` \| `float` \| `bool` \| `json` |
| updated_by / updated_at | 审计 |

唯一约束 `(scope, config_key)`。每个 scope 维护保留键 `meta.version`（int），每次保存 +1，供 agent 侧版本比对。

### 4.2 `assistant_run`（用量审计）

| 列 | 说明 |
|---|---|
| id / trace_id / session_id / user_id | 标识 |
| user_message | 截断 500 字符 |
| intent | QUERY_DATA / ANALYZE_HISTORY / GENERAL_CHAT |
| tools_called | jsonb 数组（工具名按调用序去重） |
| tool_rounds / total_tokens / duration_ms | 量化指标 |
| is_success / error_message | 结果 |

写入点：`agent.run` / `agent_stream.run` 完成后（成功与失败均落）；落库失败 try/except 吞掉记 warning，不影响对话主流程。历史数据不回填（自上线起累积）。

## 5. 中台智能助手侧

### 5.1 配置项（scope=`assistant`，代码默认值兜底）

| 键 | 类型 | 初值来源 |
|---|---|---|
| `system_prompt` | string | 现 `agent.py` SYSTEM_PROMPT（seed） |
| `intent_prompt` | string | 现 `agent.py` INTENT_RECOGNITION_PROMPT（seed） |
| `model_name` | string | `Settings.AI_OPENAI_MODEL`（provider 仍由 env 定，涉及 API Key） |
| `temperature` | float | `ChatOptions` 默认 0.7 |
| `max_tokens` | int | `ChatOptions` 默认 2048 |
| `max_tool_rounds` | int | 现 `MAX_TOOL_ROUNDS=5` |
| `tool_execute_timeout` | int（秒） | 现 `TOOL_EXECUTE_TIMEOUT=30` |
| `disabled_tools` | json 数组 | `[]` |

读取时机：每次 chat / chat/stream 请求读取（无缓存，多实例强一致；chat 本身是重请求，一次额外 SELECT 可接受）。

### 5.2 提示词-工具清单联动

`system_prompt` 支持 `{{TOOLS}}` 占位符：构建系统消息时替换为当前启用工具的名称+描述清单；不含占位符则原样使用。防止工具启停后提示词漂移。配置页对该占位符做说明。

### 5.3 工具启停生效

`tool_registry` 新增禁用过滤：`get_openai_tools_schema()` 与工具执行路径统一按 `disabled_tools` 过滤，收口在 `agent.py` / `agent_stream.py` 现有两处调用点。意图识别 prompt 不受影响。全部工具被禁用时保存报警告（Agent 无工具可用，仅闲聊）。

### 5.4 统计与监控端点（`/api/v1/system/ai-assistant/*`）

- `GET /stats?days=30`：总量、成功率、平均耗时、token 合计、每日趋势、工具命中 Top10、活跃用户数。
- `GET /runs`：分页运行记录（时间/用户/意图/工具/耗时/token/状态筛选）。
- 行级 trace 详情复用既有 `/api/v1/assistant/logs/{trace_id}`（不动现有端点与文件日志）。

## 6. aeos-execution-agent 侧

### 6.1 backend 管理端点（`/api/v1/system/execution-agent/*`）

- `GET /status`：代理调 agent `/admin/status`（10s 超时；不可达时返回明确下线态而非报错），附 `reasoning_task` 最近 10 条（复用 reasoning service 序列化逻辑的新内部查询，不走 HMAC 域）。
- `GET /config` / `PUT /config`：读写 scope=`execution_agent` 配置，保存即 bump `meta.version`。
- `POST /restart`：调 agent `/admin/restart`；前端随后轮询 `/status` 确认恢复。

### 6.2 配置拉取通道

复用数据供给 AppKey/HMAC 体系，对外接口注册表新增端点码 `agent.config`：
- `GET /external/agent/config` → `{ version, config }`（需在数据供给页为 agent 的 AppKey 勾选该端点授权；README 接入步骤同步更新）。

### 6.3 Node agent 改动

1. `config.js`：启动时 HMAC 拉取 DB 配置合并（失败用 env 值继续 + 周期重试，不阻塞启动）。
2. `index.js`：health server 监听 `127.0.0.1` → `0.0.0.0`（否则 backend 容器不可达）；新增 `/admin/status`（registered / currentRun / configVersion / uptimeS / capabilities）、`/admin/restart`（200 响应后 `process.exit(0)`），请求头 `x-admin-token` 校验（env `AGENT_ADMIN_TOKEN`）。
3. `.env.example` / compose 模板补 `AGENT_ADMIN_TOKEN`。

### 6.4 可编辑项 vs 留 env

| 进 DB（env 为兜底默认值） | 只留 env |
|---|---|
| `agent_name`、`query_timeout_ms`、`reasoning_timeout_ms`、`log_level`、`ws_url`、`agent_id` | `CONTROL_PLATFORM_BASE_URL`、`appKey/appSecret`、`EXECUTION_PLANE_TOKEN`、`AGENT_ADMIN_TOKEN`、`HEALTH_CHECK_PORT` |

### 6.5 生效语义

配置保存后 backend 不推送：agent 启动/自重启时拉取。`/admin/status` 返回已加载 version；backend 与 DB `meta.version` 比对，不一致时前端提示「配置未生效，需重启」，与重启按钮闭环。`reasoning_timeout_ms` 变更仍需同步关注中台 `REASONING_TIMEOUT_S` 的约束（README 已有说明）。

## 7. 权限、菜单与前端

### 7.1 权限（`permission_registry` 新增；admin 经 `ROLE_PERMISSION_ADDITIONS` 授予）

| code | actions | 控制 |
|---|---|---|
| `ai.assistant_monitor` | read | 看板 + 运行记录 |
| `ai.assistant_config` | read, update | 配置 Tab（页内二次校验，无此权限隐藏 Tab） |

菜单可见性：`ai.assistant_monitor` 或 `ai.assistant_config` 任一即显示「智能助手管理」（仅 config 权限的用户只看到配置 Tab）。
| `ai.execution_agent` | read, update | agent 页全部（配置与重启均为 update） |

### 7.2 菜单与路由

MainLayout 系统分组（`/backups` 旁）新增：`/ai-assistant` 智能助手管理、`/execution-agent` 执行面智能体；`contentRoutes.tsx` 同步注册。

### 7.3 页面

**`SystemCenter/AssistantManagement.tsx`**（三 Tab，Tabs 权限级联）：
- 概览：统计卡片 + 每日趋势折线 + 工具命中 Top 条形（`@ant-design/charts`）。
- 运行记录：分页表，行展开调 `/logs/{trace_id}` 展示 trace 详情。
- 配置：提示词×2 textarea（含 `{{TOOLS}}` 说明与「恢复默认」）、模型参数表单（模型名/温度/max_tokens/轮数/工具超时）、14 工具 Switch 列表。

**`SystemCenter/ExecutionAgentManagement.tsx`**：
- 状态卡：注册状态 / 当前 run / 已加载配置版本（与 DB 版本不一致标橙 + 提示重启）/ uptime。
- 配置表单（§6.4 DB 项）+ 重启按钮（Modal 二次确认，重启后自动轮询状态恢复）。
- 最近推理任务表（runId / 状态 / 耗时 / llm_called / 时间）。

## 8. 安全

- 配置写入键白名单校验（两 scope 各自合法键集，拒绝任意键）+ 值类型/长度校验。
- 配置修改写现有审计日志；敏感值永不进 DB、接口不回显。
- agent `/admin/*` 仅容器网络可达 + token 校验；`/external/agent/config` 走既有 HMAC + IP 白名单。
- 新端点全部挂 `PermissionChecker`；响应统一 `ResponseModel` 信封。

## 9. 部署与迁移注意

- 两张新表由 `create_all` 自建（生产容器每次启动跑 `init_database.py`，幂等）；seed 提示词初值写入 `init_database.py`。
- 生产 compose（`docker-compose-prod.yml`）目前只有旧 `execution-agent`；部署本功能时需把 `aeos-execution-agent` 服务补进 prod compose（含 `AGENT_ADMIN_TOKEN`），backend `.env` 增 `EXECUTION_AGENT_BASE_URL`。
- 多实例部署：配置 DB 单点天然一致；assistant 即时生效；agent 各实例重启各自拉取。
- 查询白名单三处同步约束（README 维护注意）不受本设计影响（不改 `query-adapter.js` 映射）。

## 10. 非目标

- agent 运行历史全量上报（查询类 run 仍只在本机日志）。
- 提示词版本历史 / diff 回滚。
- assistant 多 provider 运行时切换（由 env 决定）。
- 通用配置中心抽象（方案 B）。

## 11. 验证

- 后端：`python -m pytest`（含新增单测：配置白名单/版本 bump/统计聚合；不碰审批与索赔既有套件）。
- 前端：`npm run build`（唯一校验）。
- agent：`aeos-execution-agent/test/` 补 `/admin/*` 与配置拉取合并的用例；裸机 `npm start` 冒烟（healthz → admin/status → admin/restart 拉起）。
