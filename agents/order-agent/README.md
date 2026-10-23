# 订单智能体（order-agent）

只注册写能力 `update_control_platform_order`：直接写订单头四个日期字段（出货计划 / 发货完成 / 客户验货 / 上线时间），字段白名单校验，全量审计（operator 含 Hub runId）。

- 已关闭（erp_status=3）或已删除（is_deleted=1）的订单拒绝写入。
- 字段值 `YYYY-MM-DD` 或 `null`（清空），至少一个字段。
- **写操作不可撤销**：Hub 召回只中止本地等待，不会回滚已写入的数据。

## 运行

```powershell
Copy-Item .env.example .env
npm install
npm start
```

## 构建

在仓库根执行：

```powershell
docker build -f agents/order-agent/Dockerfile -t aeos-order-agent:latest agents
```

## 配置

| 变量 | 说明 |
|---|---|
| `EXECUTION_AGENT_KEY` | 固定 `order` |
| `EXECUTION_AGENT_ID` | `runtime-control-platform-order` |
| `CONTROL_PLATFORM_ORDER_APP_KEY/SECRET` | 订单写专用 API Key（`orders.schedule.update` + `agent.config`） |
| `CONTROL_PLATFORM_TIMEOUT_MS` | 单次写请求超时 |
| `HEALTH_CHECK_PORT` | 容器内 health/admin 端口，默认 8790 |
