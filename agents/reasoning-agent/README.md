# 推理智能体（reasoning-agent）

只注册 `reason_control_platform`，调用中台只读推理接口，结论带 `evidence_refs`。

## 运行

```powershell
Copy-Item .env.example .env
npm install
npm start
```

## 构建

在仓库根执行：

```powershell
docker build -f agents/reasoning-agent/Dockerfile -t aeos-reasoning-agent:latest agents
```

## 配置

| 变量 | 说明 |
|---|---|
| `EXECUTION_AGENT_KEY` | 固定 `reasoning` |
| `EXECUTION_AGENT_ID` | `runtime-control-platform-reasoning` |
| `CONTROL_PLATFORM_REASONING_APP_KEY/SECRET` | 推理专用 API Key |
| `CONTROL_PLATFORM_REASONING_TIMEOUT_MS` | 单次推理超时 |
| `HEALTH_CHECK_PORT` | 容器内 health/admin 端口，默认 8790 |
