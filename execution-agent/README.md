# execution-agent — 执行面智能体

按《执行面智能体接入契约》开发的执行面查询智能体：反向 WebSocket 连接管理面（AEOS Hub），
对外提供唯一能力 `query_control_platform`（中台只读查询，契约 §4）。设计文档见
`docs/执行面智能体-开发设计.md`。

## 架构（两进程，契约 §8 形态）

- **Node 常驻进程**（`src/`）：WS 协议状态机 —— 连接（握手头 `x-aeos-execution-token`）→
  `register` → `registered` → 周期心跳（`heartbeatIntervalMs`，缺省 5000ms）；
  `dispatch` 校验后 spawn 查询子进程回传 `run_complete` / `run_failed`；`recall` 杀子进程不回报（§5）；
  断线指数退避重连（1s→30s）后重新 register；本地 `/healthz` 健康检查（§7）。
- **Python 短命子进程**（`query/company-control-query.py`）：每次查询 spawn 一次，
  importlib 直载 `mcp-company-control/mcp_server/upstream_client.py`（契约 §4.4 权威参考），
  复用其 HMAC 签名、端点映射、信封解包与重试；stdout 单行 JSON 结果。

```
src/agent.js        入口：配置/日志/健康检查/信号处理
src/ws-client.js    WS 状态机（注册/心跳/重连）
src/runner.js       dispatch 处理（白名单校验/子进程/回传）
src/config.js       环境变量 + 契约 §4.2 白名单（18 path）
query/              Python 查询 CLI
test/               mock-hub / fake-query / e2e（均为测试桩，非管理面交付物）
```

## 快速开始（本机进程）

```powershell
npm install
Copy-Item .env.example .env      # 填值
node --env-file=.env src/agent.js
```

日志为 stdout JSON 行（`LOG_LEVEL=debug` 可见心跳）；凭证等敏感信息永不输出。

## 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EXECUTION_WS_URL` | `ws://127.0.0.1:8788/execution-agent` | 管理面控制通道 |
| `EXECUTION_PLANE_TOKEN` | （必填） | 握手头 `x-aeos-execution-token` |
| `EXECUTION_AGENT_ID` | `runtime-execution-query` | 须等于管理面 AI 港湾 Runtime id（§4.5 桥接约定） |
| `EXECUTION_SOURCE_SYSTEM` | （空=不下发该字段） | 注册来源标识（Hub 仪表盘「来源」列，如 `公司中控平台（UAT）`） |
| `AGENT_NAME` / `AGENT_VERSION` | `execution-query-agent` / package.json | 注册信息 |
| `PYTHON_BIN` | `python` | 查询子进程解释器（Windows 可配 `py` 或绝对路径） |
| `QUERY_SCRIPT` | `<本目录>/query/company-control-query.py` | 查询 CLI 路径 |
| `UPSTREAM_CLIENT_PATH` | `<仓库根>/mcp-company-control/mcp_server/upstream_client.py` | 上游客户端直载路径 |
| `QUERY_TIMEOUT_MS` | `30000` | 单次查询子进程超时（超时 SIGKILL → `UPSTREAM_TIMEOUT`） |
| `HEALTH_CHECK_PORT` | `8789`（0 关闭） | 本地 `GET /healthz`，200=已注册在线 |
| `LOG_LEVEL` | `info` | `debug` 输出心跳日志 |
| `CONTROL_PLATFORM_*` | — | 中台地址/凭证，透传子进程（HMAC 优先，见 mcp-company-control README） |

## 测试

```powershell
npm test    # 11 个 e2e 场景：注册/心跳/成功/上游失败/非法路径/未知能力/忙拒/召回不回报/崩溃/超时/重连/优雅退出
```

以 `PYTHON_BIN=node QUERY_SCRIPT=test/fake-query.mjs` 注入假查询进程，不依赖真实凭证；
`test/mock-hub.mjs` 仅为测试桩，不是管理面。

## 真实联调（mock 通过后必做）

1. SPC 管理端「基础数据中心 → 数据供给」新建 API Key，勾选 18 个端点（README of
   mcp-company-control 有清单），复制 AppKey/AppSecret。
2. `.env` 填 `CONTROL_PLATFORM_BASE_URL`（生产 `http://150.158.13.110:18084/api/v1`）、
   `CONTROL_PLATFORM_APP_KEY/APP_SECRET`。
3. `EXECUTION_WS_URL` 指向真实 Hub 控制端口，`EXECUTION_PLANE_TOKEN` 向管理面索取，
   `EXECUTION_AGENT_ID` 保持 `runtime-execution-query`。
4. 启动后确认日志 `registered`，由 Hub 侧 G1 派单，验证两种 `businessObjectRef` 推导各回传一单：
   `business://kitting/...`（齐套结果）与 `business://order/...`（订单）。

## Docker

已接入根 `docker-compose.yml`（`execution-agent` 服务，profile `agent`），默认 `docker compose up -d`
不会启动它；配置好根 `.env` 的 `EXECUTION_WS_URL` / `EXECUTION_PLANE_TOKEN` /
`CONTROL_PLATFORM_*` 后：

```powershell
docker compose --profile agent up -d execution-agent   # 首次会自动构建镜像
docker compose logs -f execution-agent
docker compose --profile agent stop execution-agent
```

或单独构建/运行（构建上下文为**仓库根**，需 COPY mcp-company-control 的 upstream_client.py）：

```powershell
docker build -f execution-agent/Dockerfile -t spc-execution-agent .
docker run --rm -e EXECUTION_WS_URL=... -e EXECUTION_PLANE_TOKEN=... -e CONTROL_PLATFORM_APP_KEY=... spc-execution-agent
```

镜像 `node:20-alpine` + python3（httpx/python-dotenv，apk/pip 走国内镜像源）；
HEALTHCHECK 走容器内 `/healthz`（200=已注册在线，503=未连上 Hub）。健康检查仅绑容器内
127.0.0.1，不对宿主机暴露。

## 维护注意

- 白名单双份维护：`src/config.js` 的 `PATH_WHITELIST` 与
  `mcp-company-control/mcp_server/upstream_client.py` 的 `_ENDPOINT_CODES` —— 契约 §4.2 变更时两处同步。
- Windows 跨进程 SIGTERM 不触发处理器：以 IPC 拉起时发 `{type:"shutdown"}` 可优雅退出；
  生产容器（Linux）`docker stop` 的 SIGTERM 正常生效。
