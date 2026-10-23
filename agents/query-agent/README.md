# 查询智能体（query-agent）

只注册 `query_control_platform`，通过 18 个冻结白名单路径只读查询中台。

## 运行

```powershell
Copy-Item .env.example .env
npm install
npm start
```

## 构建

在仓库根执行：

```powershell
docker build -f agents/query-agent/Dockerfile -t aeos-query-agent:latest agents
```

## 配置

| 变量 | 说明 |
|---|---|
| `EXECUTION_AGENT_KEY` | 固定 `query` |
| `EXECUTION_AGENT_ID` | `runtime-control-platform-query` |
| `CONTROL_PLATFORM_QUERY_APP_KEY/SECRET` | 查询专用 API Key |
| `CONTROL_PLATFORM_TIMEOUT_MS` | 单次查询超时 |
| `HEALTH_CHECK_PORT` | 容器内 health/admin 端口，默认 8790 |
