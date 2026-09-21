# company-control MCP Server

中台只读能力适配器，接入 AEOS Hub。遵循 **AEOS MCP Integration Specification v0.1.0**。

- **名称**：company-control
- **版本**：0.1.0
- **传输**：stdio（由 AEOS Hub 作为 MCP client 拉起）
- **技术栈**：Python 3.12+ / 官方 mcp SDK 2.x（`MCPServer`）/ httpx / pydantic
- **权限等级**：全部 Tool 为 `READ_ONLY`（MCP annotations `readOnlyHint=true` + `server.json` 声明）
- **维护团队**：中台平台组（版本负责人见 `server.json`，Registry 提交前补齐）

## 与规范默认栈的差异说明

规范 §2 默认 Node.js（`.mjs` + Zod）。本项目为 Python 等价实现（stdio 上 JSON-RPC 协议完全一致），
提交 AEOS Registry 审核时需登记此技术栈变更。包目录命名为 `mcp_server/` 而非 `mcp/`，
避免与 SDK 的 `mcp` 包在 `sys.path` 中冲突。

## 启动

```bash
pip install -r requirements.txt
cp .env.example .env    # 填入中台端点与凭证
python -m mcp_server    # stdio 传输；日志写 stderr
```

AEOS Hub 侧接入配置（测试环境）：

```toml
[mcp_servers.company-control]
command = "<python 解释器绝对路径>"
args = ["-m", "mcp_server"]
# 工作目录需为本项目根（mcp-company-control/），并在 Hub 侧注入上述环境变量
```

## 环境变量

见 `.env.example`：

| 变量 | 说明 |
|---|---|
| `CONTROL_PLATFORM_BASE_URL` | 中台（SPC）API 地址；生产经 nginx：`http://150.158.13.110:18084/api/v1` |
| `CONTROL_PLATFORM_APP_KEY` / `APP_SECRET` | **数据供给 HMAC API Key（生产推荐，优先级 1）** |
| `CONTROL_PLATFORM_TOKEN` | 静态 Bearer Token（优先级 2） |
| `CONTROL_PLATFORM_CLIENT_ID` / `CLIENT_SECRET` | client_credentials 凭证（优先级 3） |
| `CONTROL_PLATFORM_TOKEN_URL` | 可选，自定义令牌端点 |
| `CONTROL_PLATFORM_TIMEOUT_MS` | 请求超时，默认 15000 |
| `CONTROL_PLATFORM_CONNECT_TIMEOUT_MS` | 连接超时，默认 5000 |

## SPC 生产对接（数据供给 API Key）

生产认证走 SPC 现成的「数据供给」HMAC 签名机制：

- 请求头：`X-App-Key`、`X-Timestamp`（秒级，±300s 有效）、`X-Signature`
- 签名串：`timestamp + app_key + endpoint_code + query_string` → `HMAC-SHA256(app_secret)` hex
- `endpoint_code` 为 SPC `@exposable` 注册表代码（如 `int:health.ping`），非 URL 路径
- 路径 → endpoint_code 映射维护在 `mcp_server/upstream_client.py` 的 `_ENDPOINT_CODES`

创建密钥（SPC 管理端）：

1. 登录 SPC → 基础数据中心 → 数据供给 → 新建 API Key
2. 勾选接口：`int:health.ping`（业务端点建成后追加勾选）
3. IP 白名单：填 MCP 运行主机 IP（本地调试可留空）
4. 保存后复制 AppKey / AppSecret（**AppSecret 仅显示一次**），填入 `.env`

**当前端点状态**：SPC 已注册可暴露端点仅 `int:health.ping`（`GET /common/ping`，`get_system_health` 已对接）；
指标 / 物料 / 供应商 / 订单端点待 SPC 侧以 `@exposable` 建成后，更新 `_ENDPOINT_CODES` 映射即可。

## Tool 清单（6 个，全部 READ_ONLY）

| Tool | 说明 | 关键约束 |
|---|---|---|
| `get_system_health` | 连接自检 | 返回状态/版本/capabilities（顶层字段超集，§16） |
| `catalog_metrics_list` | 指标目录 | 分页 ≤100 |
| `metric_query` | 指标查询 | 日期跨度 ≤92 天；`dimension` 枚举 day/week/month；返回 `data_as_of` |
| `master_material_search` | 物料检索 | 关键词 2–80 字符；敏感字段脱敏 |
| `master_supplier_get` | 供应商详情 | 编码必填；404 → `NOT_FOUND` |
| `detail_orders_list` | 订单明细分页 | 必须至少一个过滤条件；单页 ≤100 |

- 全部 Tool 拒绝未定义字段（严格 Schema，`additionalProperties: false`），带 `readOnlyHint` 标注
- 数据类 Tool 支持可选 `request_id`（≤64 字符）透传上游并在返回包回显，便于审计与链路追踪
- 上游返回 `stale: true` 时统一返回 `STALE_DATA`（retryable），`data_confidence=low` 透传

## 输入输出示例

调用 `metric_query`：

```json
{"metric_code": "OTD", "date_from": "2026-09-01", "date_to": "2026-09-19", "dimension": "day"}
```

返回（规范 §8 标准包）：

```json
{
  "source": "company-control",
  "capability": "metric_query",
  "read_only": true,
  "generated_at": "2026-09-20T08:00:00Z",
  "data_confidence": "medium",
  "data_as_of": "2026-09-19T18:00:00Z",
  "evidence_refs": ["control-platform://metric/OTD@2026-09-19T18:00:00Z"],
  "data": [{"date": "2026-09-18", "value": 96.5}]
}
```

错误（规范 §12）：

```json
{
  "source": "company-control",
  "error": {"code": "UPSTREAM_TIMEOUT", "message": "中台端点 /metric 响应超时（>15000ms）", "retryable": true, "occurred_at": "2026-09-20T08:00:00Z"}
}
```

## 测试

```bash
python scripts/test_company_control.py
```

内置 mock 中台端点，覆盖规范 §20 十二条 + STALE_DATA 补充（共 13 项：握手 / tools/list / 结构化返回 / 非法输入（含未定义字段与非法枚举）/ 未授权 / 超时 / 不可用不崩溃 / evidence / 脱敏 / 无写工具 / 幂等 / 健康检查 / 数据过期）。

## 元数据与权限声明

- `server.json`：Server 元数据（name / version / owner / transport / read_only / required_permissions / 依赖 / 维护团队 / 每 Tool 权限等级），提交 AEOS Registry 使用
- MCP 协议层：`serverInfo.version=0.1.0`；每个 Tool 带 `annotations.readOnlyHint=true`

## 上游系统依赖

SPC 后端（`CONTROL_PLATFORM_BASE_URL`），通过「数据供给」HMAC API Key 调用：

- 已就绪：`GET /common/ping`（`int:health.ping`）
- 待建设（`@exposable`）：`/metrics`、`/metric`、`/material`、`/supplier`、`/orders`
- 业务端点响应体携带 `data_as_of` 与 `data_confidence`（T+1 数仓 → `medium`）
- 调用方需在 API Key 上勾选对应 endpoint_code + IP 白名单

## 已知限制

- 仅只读；写操作 Tool 待 AEOS Guard 审批流成熟后再评估
- 业务数据端点（指标/物料/供应商/订单）SPC 侧尚未注册可暴露接口，当前仅健康检查可端到端联调
- 明细单页上限 100 条，更大结果暂不支持异步下载句柄（规划中 `query_id`）
- 静态 Token 与 client_credentials 二选一；令牌轮换依赖中台侧配置

## 目录结构

```
mcp-company-control/
├─ mcp_server/            # Server 包（避免与 SDK 包 mcp 同名）
│  ├─ __main__.py         # 入口：python -m mcp_server
│  ├─ server.py           # Tool 注册与实现
│  ├─ upstream_client.py  # 中台端点客户端（超时/错误映射/受限重试）
│  └─ contracts.py        # 标准返回包/错误/Evidence/脱敏
├─ scripts/test_company_control.py
├─ requirements.txt / .env.example / CHANGELOG.md
```
