# 执行面智能体

`gateway-agent` 是 SPC 对 AEOS Hub 的唯一身份、唯一 HTTP 出口、**唯一执行面**；Hub 与 SPC 助手是它的两个调用方：

- `gateway-agent`：唯一 Hub WS 身份 `gateway-control-platform`，注册 `query_control_platform` / `reason_control_platform` / `write_control_platform`；内置 `query-agent` / `reasoning-agent` / 订单写适配器；代理借调、能力目录、assistant-events。**必须单副本**，多副本会以同一 `agentId` 重复注册 Hub。
- `query-agent` / `reasoning-agent`：仅作为网关内部 adapter 复用，不再独立部署、不再直连 Hub。
- 订单写：Hub 审批派单（WS dispatch）与 SPC 助手人工确认（本地 `/admin/run` + actor token）路由到同一个内部 Agent `spc-agent-order-write`；本地 run 不占 Hub 派单槽位，不产生 `AGENT_BUSY` 争用。**写操作不可撤销，召回只中止等待，不会回滚已写入的字段。**

## 内部逻辑 Agent 与 Hub 归因

`gateway-agent` 内部维护 Agent 注册表，按 `capability + input.task_type` 路由：

| task_type | agentId | role |
|---|---|---|
| `order_delivery_analysis` | `spc-agent-order-risk` | `order_risk` |
| `material_kitting_analysis` | `spc-agent-kitting-risk` | `kitting_risk` |
| `quality_analysis` | `spc-agent-quality-risk` | `quality_risk` |
| `production_analysis` | `spc-agent-production-risk` | `production_risk` |

- 推理任务的 `run_complete.result.handled_by` 返回上述身份，`model` 取后端实际 `llm.model`；
- 查询不返回 `handled_by`，Hub 记 null；
- `request_id` 从 dispatch 顶层或 `input` 提取并原样回显；
- `target_agent_ref` 为内部 `agentId`，找不到或不匹配返回 `TARGET_AGENT_UNAVAILABLE`；
- 忙碌 / 并发上限返回 `AGENT_BUSY`，无匹配内部 Agent 返回 `AGENT_NOT_FOUND`。

## 受控写操作（Hub 审批 / SPC 助手确认）

`write_control_platform` 由网关内部订单写 Agent `spc-agent-order-write` 执行，Hub 与 SPC 助手共用同一 adapter、同一操作注册表与同一后端端点 `PUT /external/orders/{order_no}/write`（`orders.write`）。

**操作注册表（唯一源）**：`agents/shared/order-write-operations.json`——操作清单、`audiences`（hub / assistant）、字段→列映射、校验与 ERP 守卫全部声明驱动；adapter、网关路由、后端 write_service、助手工具四端共同消费。新增「字段写入类」操作只需在注册表加一项。

| operation | audiences | changes | 规则 |
|---|---|---|---|
| `order.update_note` | hub | `{"remark": "..."}` | 覆盖写，≤2000 字符，空串/null 清空；允许已关闭订单，禁止已删除订单 |
| `order.update_status` | hub | `{"status": "open"\|"closed"}` | 同时写 `sale_order.status` + `is_closed`；`erp_status=3` 或已删除订单拒绝 |
| `order.update_delivery_date` | hub | `{"deliveryDate": "YYYY-MM-DD"}` | 写 `sale_order.promised_date`（合同交期）；允许过去日期纠错；`erp_status=3` 或已删除订单拒绝；不自动改出货计划/下游任务 |
| `order.update_schedule_fields` | assistant | `{"fields": {"promised_date": "...", ...}}` | 五日期字段任意组合；至少一个；允许过去日期；`erp_status=3` 或已删除订单拒绝；不自动改下游任务 |

- 能力声明带顶层 `operations` 元数据（name/title/keywords/changesField/fields，注册表 hub 项自动生成），Hub 对话按它解析操作、订单号与目标值；`audiences` 不含 hub 的操作不暴露给 Hub；
- 幂等：调用方必须传 `idempotencyKey`（缺省回退 `request_id`）；后端 `orders.write` 用 `order_write_idempotency` 表保证同一 key 只执行一次，重复返回 `idempotent_replay=true`，内容不一致返回 `IDEMPOTENCY_CONFLICT`；
- 返回：`ok` / `operation` / `target` / `before` / `after` / `appliedAt` / `idempotent_replay` / `handled_by` / `request_id`；
- 鉴权三层：网关 admin token（backend→网关 `/admin/run`）、actor token（助手能力校验，透传至 `orders.write`）、数据供给 AppKey 签名（网关→backend）；
- 数据供给 Key 需授权 `orders.write`（订单写 AppKey）。

## 本地运行

依赖 Node 20，在 `agents/` 下安装 workspace 依赖：

```powershell
npm install
```

网关按仓库根 `.env.example` 第 12 节在 `gateway-agent/.env` 配置环境变量（`EXECUTION_WS_URL` 置空为本地模式），然后：

```powershell
npm run start -w gateway-agent
```

## 测试

```powershell
npm test
```

## 构建镜像

```powershell
docker build -f agents/gateway-agent/Dockerfile -t aeos-gateway:latest agents
```

`query-agent` / `reasoning-agent` 的 Dockerfile 仅保留作本地调试，不再部署。

## 部署

```powershell
docker compose --profile aeos up -d aeos-gateway
```

`aeos-gateway` 通过 `backend/certs/caddy-root.crt` 信任 Hub 私有 CA（`NODE_EXTRA_CA_CERTS`），并挂载为只读证书。
