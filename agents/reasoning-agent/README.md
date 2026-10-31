# 推理智能体（reasoning-agent）

只注册 `reason_control_platform`，把 Hub 的推理派单转发到中台推理接口；结论带 `evidence_refs`，召回时同时中止本地请求并取消中台任务。

## 链路

```text
Hub WS dispatch
  → reasoning-agent（HMAC）
  → POST /api/v1/external/reasoning/analyze
  → 中台只读证据采集 + 大模型结构化输出
  → run_complete.result（summary / conclusions / evidence_refs / data_as_of / usage）
```

## 中台前置条件

1. 后端配置真实大模型：`AI_DEFAULT_PROVIDER=openai`、`AI_OPENAI_BASE_URL`、`AI_OPENAI_API_KEY`、`REASONING_MODEL=deepseek-flash`，重启 backend。
2. 「数据供给管理」创建推理专用 API Key，勾选：
   - `reasoning.analyze`
   - `reasoning.cancel`
   - `reasoning.task`
3. 记录 `app_key` / `app_secret`，通过安全渠道交给 Sidecar 部署方；不要写入仓库。

## 配置

复制 `.env.example` 为 `.env`，按实际环境填写：

| 变量 | 说明 |
|---|---|
| `EXECUTION_AGENT_KEY` | 固定 `reasoning` |
| `EXECUTION_WS_URL` | Hub 执行面 WS 地址；留空为本地模式（只开 `/admin/*`，不连 Hub） |
| `EXECUTION_PLANE_TOKEN` | legacy 根令牌；运行时必填（即使本地模式） |
| `EXECUTION_SYSTEM_ID` / `EXECUTION_SYSTEM_TOKEN` | 每系统令牌握手；两项同时配置时优先于根令牌 |
| `EXECUTION_AGENT_ID` | `runtime-control-platform-reasoning` |
| `EXECUTION_AGENT_NAME` | `公司中台推理智能体` |
| `CONTROL_PLATFORM_BASE_URL` | 中台后端地址，到 `/api/v1` 为止；compose 内为 `http://backend:8000/api/v1`，外部为 `https://<主机>:18085/api/v1` |
| `CONTROL_PLATFORM_REASONING_APP_KEY` | 推理专用 API Key |
| `CONTROL_PLATFORM_REASONING_APP_SECRET` | 推理专用 API Secret |
| `CONTROL_PLATFORM_REASONING_TIMEOUT_MS` | 单次推理 HTTP 超时，默认 `180000`（服务端 170s） |
| `HEALTH_CHECK_PORT` | 容器内 health/admin 端口，默认 `8790` |
| `AGENT_ADMIN_TOKEN` | 管理面令牌，与 backend 的 `AGENT_ADMIN_TOKEN` 一致 |
| `LOG_LEVEL` | 日志级别，默认 `info` |

## 启动

本地：

```powershell
Copy-Item .env.example .env
npm install
npm start
```

Docker（仓库根）：

```powershell
docker compose --profile aeos up -d
```

## 联调确认

1. Hub 执行面显示 `runtime-control-platform-reasoning` 在线，能力 `reason_control_platform` 可用。
2. Hub 派单的 `runId` 作为 `task_id` 传给中台；响应的 `task_id` 应与之相等。
3. 结果包含 `conclusions`、`evidence_refs`、`data_as_of`（带 `+08:00`）、`usage`。
4. 召回时 Sidecar 发送 `POST /external/reasoning/tasks/{runId}/cancel`；中台任务终态为 `cancelled`。
5. 中台审计表 `reasoning_task` 中 `llm_called=1`，并记录 `llm_provider/model/latency_ms`。

## 常见错误

| 现象 | 排查 |
|---|---|
| HTTP 401 | 缺少 `X-App-Key/X-Timestamp/X-Signature`，或系统时间偏差超过 300s |
| HTTP 403 | 签名串错误、Key 未勾选对应 endpoint、IP 不在白名单 |
| 信封 503 | 中台未配置真实大模型（`AI_DEFAULT_PROVIDER=rule_based` 或模型调用失败） |
| 信封 404 | 业务锚点无证据（不代表无风险），或 cancel/status 的任务不存在 |
| 信封 409 | 同 `task_id` 的任务仍在运行，稍后查询状态 |
| 信封 490 | 任务已被取消；Hub 召回场景按正常取消处理，不报 `run_failed` |
| 信封 504 | 超过 `REASONING_TIMEOUT_S`（默认 170s） |
