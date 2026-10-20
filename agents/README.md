# 执行面多智能体

三个独立 Agent，共用 `runtime` 包：

- `query-agent`：`query_control_platform`，18 个只读查询路径。
- `reasoning-agent`：`reason_control_platform`，只读推理。
- `order-agent`：`update_control_platform_order`，**写能力**——直写订单头四个日期字段（出货计划 / 发货完成 / 客户验货 / 上线时间），字段白名单校验，全量审计。**写操作不可撤销，召回只中止本地等待，不会回滚已写入的字段。**

## 本地运行

```powershell
npm install
cd query-agent
Copy-Item .env.example .env
npm start
```

## 测试

```powershell
npm test
```

## 构建镜像

```powershell
docker build -f agents/query-agent/Dockerfile -t aeos-query-agent:latest agents
docker build -f agents/reasoning-agent/Dockerfile -t aeos-reasoning-agent:latest agents
docker build -f agents/order-agent/Dockerfile -t aeos-order-agent:latest agents
```

## 部署

```powershell
docker compose --profile aeos up -d aeos-query-agent aeos-reasoning-agent aeos-order-agent
```

回退到旧合并 Agent：

```powershell
docker compose --profile aeos stop aeos-query-agent aeos-reasoning-agent
docker compose --profile aeos-legacy up -d aeos-execution-agent
```

回退期间旧 Agent 走旧管理端点 `/api/v1/system/execution-agent/*`（当前管理页不展示旧 Agent，
需通过 API 或临时回滚 backend/frontend 镜像管理；旧端点将在验收后删除）。
