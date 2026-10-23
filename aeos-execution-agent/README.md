# aeos-execution-agent — AEOS Hub 执行面智能体（查询 + 推理）

> 已被 `agents/query-agent` + `agents/reasoning-agent` 取代，保留用于切换回退；验收后删除。

独立 Sidecar，把中台（SPC）的两类只读能力经 AEOS 执行面 WebSocket 协议暴露给 AEOS Hub：

| 能力名 | 适配器 | 状态 |
|---|---|---|
| `query_control_platform` | `src/adapters/query-adapter.js` | 已联通（契约 §4.2 冻结 18 路径 + `/common/ping` 白名单，HMAC） |
| `reason_control_platform` | `src/adapters/reasoning-adapter.js` | 已联通（真实实现，REST 契约见 `docs/aeos-reasoning-api-contract.md`） |

与既有 `execution-agent/`（仅查询）的关系：本包是其**继任者**（查询 + 推理合一）。
WS 信封、握手头、心跳、召回语义、重连阶梯均对齐 `execution-agent/src/ws-client.js`
（真实 Hub 联调过的参照实现）；待本包真实联调通过后，`execution-agent/` 可退役。

## 协议要点（对齐真实契约）

- 连接握手头 `x-aeos-execution-token`；`register`（agentId/name/version/sourceSystem/capabilities）。
  管理面 127b013 起强校验**能力自描述**：每个 capability 必带 `readOnly: true`、
  `constraints`（query `{readOnly:true}` / reasoning `{readOnly:true, requireEvidence:true}`）与
  `inputSchema`/`outputSchema`（JSON Schema，随适配器维护），缺失时派单被拒（`WRITE_FORBIDDEN`）；
  身份对齐：`EXECUTION_AGENT_ID=runtime-control-platform-agent`、`EXECUTION_AGENT_NAME=公司中台执行面智能体`。
- Hub 回 `registered{heartbeatIntervalMs}` → 周期 `heartbeat{status: working|idle, currentRunId?}`
- `dispatch{runId, capability, input}` → 回 `run_update{running}` → `run_complete{result}` / `run_failed{error{code,message}}`
- 执行步骤上报：派单接受后发 `run_received`，每个中台调用前后发 `step_started` / `step_completed`
  （失败发 `error`），收尾前发 `run_summary`；事件按 runId 内 seq 递增、eventId 唯一，
  Hub 回 `run_event_ack`（仅排查用，不阻塞任务）
- `recall{runId}` → 中止本地请求 + 调中台 cancel（推理任务同步取消），**不回报**
- 断线杀活动 run（不回报），1/2/5/10/30s 阶梯 + ±20% 抖动重连后重新 register
- 单活动 run：忙时新 dispatch 回 `run_failed(INTERNAL_ERROR 'agent busy')`（契约设计 §3 边界决策，
  推理最长约 2 分钟期间查询会被忙拒——Hub 侧串行派单即无感知）
- 错误码集（契约 §12）：INVALID_ARGUMENT / UNAUTHORIZED / FORBIDDEN / NOT_FOUND / RATE_LIMITED /
  UPSTREAM_TIMEOUT / UPSTREAM_UNAVAILABLE / INTERNAL_ERROR（中台信封码自动映射）

## 目录

```
src/
├── index.js                        # 入口：能力路由 / 活动run中止联动 / healthz / 信号处理
├── protocol.js                     # WS 状态机（register/心跳/派单/召回/重连/步骤上报）
├── config.js                       # 环境变量加载（命名与 execution-agent 一致）
├── adapters/
│   ├── query-adapter.js            # 查询：{path, params}，冻结白名单 + path→endpoint_code 映射
│   └── reasoning-adapter.js        # 推理：dispatch.input → analyze；召回 → cancel；490 不回报
└── lib/
    └── http-client.js              # HMAC 签名 + 信封解包 + 错误码映射 + 受限重试
```

## 接入步骤

1. **中台凭据**：SPC 管理端「基础数据 → 数据供给」新建 API Key，勾选：
   - `reasoning.analyze` / `reasoning.cancel`（推理）
   - `agent.config`（运行时配置拉取，管理台对接用）
   - 契约 §4.2 查询端点（orders.list、kitting.results、quality_issues.list 等 18 项 + `int:health.ping`）
   记录 AppKey/AppSecret，必要时配 IP 白名单（Sidecar 出口 IP）。

2. **配置**：`cp .env.example .env` 并填写。要点：
   - `EXECUTION_WS_URL` / `EXECUTION_PLANE_TOKEN` / `EXECUTION_AGENT_ID`（Hub 分配；切流前勿复用
     `runtime-execution-query`，避免与 execution-agent 双注册同一身份）
   - `CONTROL_PLATFORM_BASE_URL` **含 `/api/v1`**（与 execution-agent 约定一致）
   - `CONTROL_PLATFORM_REASONING_TIMEOUT_MS` ≥ 中台 `REASONING_TIMEOUT_S`×1000 + 60s

3. **运行**：

   ```powershell
   # 裸机（Node ≥ 20）
   npm install
   npm start
   # 或独立 compose（build 不依赖 .env；up 前必须配好 .env）
   docker compose build
   docker compose up -d
   # 或仓库根 profile
   docker compose --profile aeos up -d aeos-execution-agent
   ```

4. **验证**：
   - 日志出现 `hub_registered`；`curl 127.0.0.1:8790/healthz` 返回 200；
   - Hub 派 `reason_control_platform` 单后，中台 `reasoning_task` 表出现以 `runId` 为 `task_id`
     的记录且 `llm_called=1`（证明真实调用大模型，非直查 REST 伪装）；
   - Hub 召回后中台任务终态应为 `cancelled`（本地不回报，符合契约 §5）。

5. **管理台对接**：根 `.env` 同步配 `AGENT_ADMIN_TOKEN`（与 backend 侧一致）；
   backend 配 `EXECUTION_AGENT_BASE_URL=http://aeos-execution-agent:8790` 后，
   系统管理「执行面智能体」页可看状态/改配置（重启后生效）/远程重启。

## 维护注意

- 查询白名单 path→endpoint_code 映射**三处同步**：本包 `query-adapter.js` /
  `mcp-company-control/mcp_server/upstream_client.py::_ENDPOINT_CODES` / SPC 对外接口注册表；
  契约 §4.2 变更时三处一起改。
- 中台推理超时/并发默认值（`REASONING_TIMEOUT_S=120`、`REASONING_MAX_CONCURRENT=5`）变更时，
  同步调整本包 `CONTROL_PLATFORM_REASONING_TIMEOUT_MS`。
