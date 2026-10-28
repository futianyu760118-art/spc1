# AGENTS.md

> 本文件供在此仓库工作的 OpenCode 会话阅读，动手前必读。

## 命令速查

### 后端（在 `backend/` 下运行，Python 3.12）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000        # 入口：app/main.py
python init_database.py                          # 幂等建表/迁移，改 schema 前必读「数据库与迁移」
```

### 前端（在 `frontend/` 下运行，Node 20）

```bash
npm install
npm run dev        # Vite dev server :3000，代理 /api 与 /uploads 到 :8000
npm run build      # = tsc -b && vite build，唯一 typecheck，交付前必跑
```

### Docker

- 本地开发（仓库根）：`docker-compose up -d` —— backend :8000、frontend :3000。
- 生产部署（部署脚本使用）：`docker compose -f docker-compose-prod.yml up -d` —— 自带 postgres/redis，backend :18085、frontend :18084。
- AEOS 执行面（`aeos` profile）：`docker compose --profile aeos up -d aeos-gateway aeos-order-agent` —— 单一网关 + 本地订单 Agent；网关必须单副本。
- backend 容器启动命令：生产为 `python init_database.py && uvicorn ...`（每次启动自动迁移）；本地 dev compose 只跑 uvicorn，需手动执行 `python init_database.py`。

### 部署（Windows 本机，多服务器并行）

```bash
powershell -ExecutionPolicy Bypass -File scripts\deploy-remote.ps1 -NonInteractive
```

- 服务器列表/角色（full=全套含 postgres/redis，app=仅应用连主库）/各台 .env 在 `scripts/deploy-config.ps1` 的 `$DEPLOY_SERVERS` 数组；`-Servers main,app1` 只部署部分，`-KeepRemoteEnv` 保留远程 .env。
- 部署脚本会构建并随镜像包上传 `aeos-gateway:latest`，并把 `backend/certs/caddy-root.crt` 随配置包上传（网关只读挂载）；网关属于 `aeos` profile，部署后需在 full 服务器按需启动（`docker compose --profile aeos up -d aeos-gateway aeos-order-agent`），保持单副本。
- 版本回退：`powershell -File scripts\manage-version.ps1 -Server <名称> list | rollback <版本名> | cleanup`。
- `.env`（含数据库/Redis/ERP 密码）与 SSH 密钥永不进仓库。

### 默认账号

密码均为 `admin123`：`admin`、`planner01`、`purchaser01`、`manager01`、`purchase_mgr01`。
登录端点：`POST /api/v1/basicdata/auth/login`（form-urlencoded，字段 `login_type` = `employee` | `supplier`）。

## 代码整洁与防重复守则（所有代码改动适用）

写任何代码前、中、后必须遵守；违反须在交付前自我纠正。

### 动手前：先查再写

- 写任何新函数/组件/工具类之前，先在代码库中搜索是否已有相似实现（按功能关键词、相似命名、相邻模块查找）；有就复用或扩展，禁止重复造轮子。
- 新增第三方依赖前，先确认标准库和项目现有依赖无法满足；能不加就不加。
- 修改代码前先读上下文（同目录相邻文件、import、调用方），理解并遵循项目现有约定（命名风格、错误处理、返回结构、目录组织），不另起炉灶。
- 需求有歧义时先提问澄清，不靠猜。

### 写代码时：整洁铁律

- DRY：同一段逻辑禁止复制第二次；出现第二处相似即提取为公共函数/组件/常量，并替换所有调用点。
- 但不过度抽象：只有单一调用方的逻辑不预先提取（Rule of Three）；禁止为"将来可能用到"写代码（YAGNI）。
- 命名见名知义、与项目风格一致：禁止 `data1` / `tmp` / `foo` / `handle2` 这类命名；布尔值用 is/has/can 前缀；函数名用动词，类/名词用名词。
- 函数单一职责：一个函数只做一件事；超过约 40 行或嵌套超过 3 层必须拆分；参数超过 3 个时收拢为对象/配置。
- 不留任何"代码垃圾"：不留 `console.log` / `print` / 调试输出；不留注释掉的旧代码（git 有历史，直接删）；不留无用 import、无用变量、空 catch、空函数；不写复述代码的废话注释，注释只解释"为什么"。
- 最小改动原则：只改与当前任务相关的代码；不顺手重排格式、不重构无关文件、不修改无关空行，保证 diff 干净可审。

### 交付前：自查清单（逐项执行）

- 全局搜索本次新写的函数名/关键代码片段，确认与已有代码无重复；发现重复立即合并。
- 删除所有调试代码、临时代码、被注释的旧实现。
- 运行项目的校验命令并确保通过（前端 `npm run build`；后端见「测试与验证」）。
- 新代码的错误处理、日志、边界情况与项目现有模式一致。
- 汇报改动时说明：改了哪些文件、为什么、复用了哪些已有代码。

### 硬性禁令

- 禁止复制本会话早前写的或代码库已有的代码片段来"快速实现"新功能。
- 禁止"先这样，以后再改"：写出来就必须是最终正确形态。
- 禁止引入项目中未使用的框架、模式或架构；与代码库保持一致，不炫技。
- 禁止在未说明的情况下留下 TODO；留 TODO 必须写清原因和负责人。

## 数据库与迁移（改 schema 前必读）

有两套 schema 机制，且二者不等价：

1. **`backend/init_database.py` 是运行时事实来源。** 它执行 `Base.metadata.create_all`，并维护手工的 `migrate_columns` 字典跑 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / 删列；生产 compose 每次容器启动都会执行且幂等。**只写成 Alembic 迁移的新列，容器重启后不会出现**，除非同时登记进 `init_database.py`（或该表由 `create_all` 全新建出）。
2. **Alembic**（`backend/alembic/`，约 50 个迁移文件）存在但**启动时不跑**，仅按需手动使用；`alembic.ini` 里硬编码的 DB URL 与 `.env` 有漂移。

加列的正确姿势：SQLAlchemy model 与 `init_database.py` 的 `migrate_columns[table]` 同时加 —— 这是本仓库主流且经过验证的做法。

模型位于 `backend/app/models/<domain>/`。`alembic/env.py` 通过 import `app.models` 把所有表注册到 `Base.metadata`；新增模型模块必须在那里（或经包 `__init__`）被 import，否则 `create_all` 看不到。

- 应用代码走**异步** SQLAlchemy（asyncpg），用 `app/core/database.py` 的 `get_db()`：**成功自动 commit、异常自动 rollback** —— 端点内不要手动 commit，除非自己接管 session。
- Alembic / `init_database.py` / ERP 读取走**同步**引擎（psycopg2、pyodbc）。

## 环境与配置

- `app/core/config.py`（`Settings`，pydantic-settings）按 `_ENV_FILES` 顺序加载：仓库根 `.env.local` → 仓库根 `.env` → CWD `.env.local` → CWD `.env`（后加载覆盖先加载）。从 `backend/` 启动 uvicorn 时实际生效的是 `backend/.env.local`（覆盖仓库根 `.env`）；Docker 由 compose 的 `${VAR}` 替换从仓库根 `.env` 注入。两份 `.env` 指向不同 DB 主机，别假设哪个在生效。
- `get_settings()` 带 `@lru_cache` —— 配置在进程生命周期内固定，改 env 需重启。
- Secrets（DB 凭据、`AI_OPENAI_API_KEY`）存在于 `.env`、`backend/.env.local`，`alembic.ini` / `config.py` 里还有已提交的默认值。**永远不要打印、记录或提交新 secret**；一律经 `Settings` 引用，禁止硬编码。

## 后端约定

### 响应结构（客户端强制）

前端 axios 拦截器（`frontend/src/services/api.ts`）把 `response.data.code !== 0` 视为失败。成功端点必须返回 `{ code, message, data }`（见 `app/schemas/common.py` 的 `ResponseModel` / `PageResult`）。裸 list/dict 即使 HTTP 200 也会被前端判为失败。

### 路由

所有路由挂载在 `/api/v1` 下（`API_PREFIX`），子路由在 `app/api/v1/__init__.py` 汇总。领域：`approval, assistant, basicdata, common, dashboard, exception, external, material, order, production, purchase, quality, rules, system, writeback`。

### 认证与权限

- **JWT + 两层失效机制**：token 携带 `login_version` 与 `jti`；`app/core/dependencies.py` 的 `get_current_user` / `get_current_user_or_share` 会拒绝 `login_version` 与 DB 不符、或 `jti` 在黑名单（`app/core/token_blacklist.py`，Redis）里的 token。重新登录会 bump `sys_user.login_version`；强制登出响应带 `X-Force-Logout: true`。
- **分享 token**（JWT 中 `share: true`）绕过权限与 `login_version` 校验 —— 分享可访问的路由用 `get_current_user_or_share`。
- 权限是角色维度的 dict（`role.permissions = {resource: [actions]}`），在 `init_database.py` seed，运行时经 `merge_role_permission_additions` 合并；`permission_registry` 每次启动（lifespan）重新同步到 DB。**`seed_roles` 只在创建角色时写 `permissions`** —— 已存在的角色只刷新 `role_name`，所以「角色管理」里的运行时授权能扛住容器重启。不要恢复旧的 `role.permissions = role_data["permissions"]` 覆盖写法；新的基础权限加到 `ROLE_PERMISSION_ADDITIONS`（`app/core/permissions.py`）。

### 后台任务

`app/main.py` lifespan 启动**七个**后台任务：ERP 同步（`basicdata.sync_scheduler`）、风险扫描（`exception.risk_scheduler`）、超期检查（`scheduler.overdue_checker`）、产能同步（`scheduler.capacity_sync_scheduler`）、数据供给预警（`scheduler.data_supply_alert`）、审批超时提醒（`scheduler.approval_timeout_reminder`）、回写 Worker（`basicdata.writeback_worker`）。它们**不是 APScheduler**（`apscheduler` 依赖在 `requirements.txt` 里闲置）：每个都是手写 `asyncio.create_task` + `while running: await asyncio.sleep(...)` 循环，随应用启停 —— import `main` 即会在启动时拉起。

### JSON 序列化

`main.py` 用 `SafeJSONResponse` 覆盖默认 JSON 响应类，容忍非 UTF-8 / `Decimal` / `datetime`。不要绕过它。

### ERP 集成

ERP 集成是 SQL 驱动的：同步 SQL 与字段映射存在 `sync_sql_config` / `field_mapping` 表，可在运行时编辑；手动触发 `POST /api/v1/basicdata/sync/...`。**ERP 同步只覆盖 `data_source = 'erp'` 的行，永不碰 `manual` / `excel` 行；改 `app/services/basicdata/` 的同步代码时必须保留此守卫。**

### 执行面（AEOS 单一网关）

- **唯一 Hub 身份**：`agents/gateway-agent` 以 `gateway-control-platform` 注册，是 SPC 唯一的 Hub WS 连接；能力固定 `query_control_platform` / `reason_control_platform`。网关必须单副本（多副本会重复注册同一 `agentId`）。
- **旧 Agent 收敛**：`query-agent` / `reasoning-agent` 仅作为网关内部 adapter 复用，不再独立部署或直连 Hub；`order-agent` 仅本地 `/admin/run`（`EXECUTION_WS_URL=""`），不连 Hub。
- **内部逻辑 Agent**：`agents/gateway-agent/src/agent-registry.js` 按 `capability + input.task_type` 路由；推理结果在 `run_complete.result.handled_by` 返回 `spc-agent-order-risk` / `spc-agent-kitting-risk` / `spc-agent-quality-risk` / `spc-agent-production-risk`（`model` 取实际 `llm.model`）；查询不返回 `handled_by`。`request_id` 从 dispatch 顶层或 `input` 提取并原样回显；`target_agent_ref` 为内部 `agentId`，找不到或不匹配返回 `TARGET_AGENT_UNAVAILABLE`。
- **错误码**：忙碌/并发上限 `AGENT_BUSY`（可重试）；无匹配内部 Agent `AGENT_NOT_FOUND`；显式 target 不可用 `TARGET_AGENT_UNAVAILABLE`；不得回退全量数据或静默成功。
- **出站边界**：所有 Hub HTTP（借调、能力目录、assistant-events）统一经网关白名单代理 `/internal/hub/*`；backend `hub_client` / `hub_reporter` 只能走 `app/services/gateway_client.py`，不得恢复直连 Hub 的第二出口。
- **入站 caller 路由**：网关调内网 `POST /api/v1/internal/gateway/resolve-caller`（`X-Gateway-Token` 鉴权）解析 `caller` 并签发 actor token；审计写 `gateway_dispatch_log`，fail-closed。`caller.userId` 按 `GATEWAY_CALLER_USER_ID_FIELD` 解析，默认 `emp_code`。`caller.systemId` 非空且不等于 `control-platform`（如 Hub 页面派单的 `aeos-hub`）按外部 caller 处理：保留元数据、按系统级执行，不映射 SPC 用户。nginx 对 `/api/v1/internal/` 一律 deny，仅 Docker 内网可达。
- **关键 env**：backend `GATEWAY_BASE_URL` / `GATEWAY_INTERNAL_TOKEN` / `GATEWAY_CALLER_USER_ID_FIELD`；gateway `GATEWAY_AGENT_ID` / `GATEWAY_AGENT_NAME` / `BACKEND_INTERNAL_BASE_URL` / `AEOS_HUB_BASE` / `AEOS_SYSTEM_ID` / `AEOS_SYSTEM_TOKEN` / `AEOS_HUB_CA_CERT` / `NODE_EXTRA_CA_CERTS`；`EXECUTION_QUERY_AGENT_BASE_URL` / `EXECUTION_REASONING_AGENT_BASE_URL` 均指向网关。
- **命令**：`docker build -f agents/gateway-agent/Dockerfile -t aeos-gateway:latest agents`；`cd agents && npm install && npm test`。改网关 / resolver / 审批中心代码后跑 `python -m pytest` 与 `npm test`。

### 审批中心（approval）

- **构成**：待办工作台（待我审批 / 我已审批 / 我发起的 三 Tab）+ 审批链配置，独立一级菜单。
- **接入新业务（builtin）**：在 `backend/app/services/common/approval_providers.py` 注册 provider（`biz_type` / 名称 / 归一化取数函数，参考 supplier_claim）。
- **接入新业务（SQL 零开发）**：管理员在「审批配置 → 业务接入」用只读 SQL + 字段映射注册（`GET/POST/PUT /api/v1/approvals/businesses`、`POST /api/v1/approvals/businesses/test-sql`）；取数 SQL 限单条 SELECT/WITH、5s 语句超时、强制 LIMIT 200，保存前实跑校验（列存在、`id` 可转整数）；字段映射必需 `id`（数字主键，全链路沿用整数 ID）/ `no` / `title` / `applicant` / `submitted_at` / `current_node`，可选 `summary` / `amount`。SQL 业务只聚合与深链跳转（无动作适配器，中心内审批被拒 `can_act=false`），超时提醒照常。
- **聚合端点**：`GET /api/v1/approvals/pending` 自动聚合（分页 + keyword / biz_type / provider_mode（builtin|sql，接入方式筛选）/ 日期 / wait_level / today_only 筛选；返回 `stats` 且 stats 恒为全量口径）。
- **provider 可选能力**：`fetch_approved` / `fetch_submitted` / `preview` / `approve` / `reject` / `recall`；未实现的业务只做聚合与深链跳转。
- **审批动作**：可在中心内联完成 —— `POST /api/v1/approvals/items/{biz_type}/{id}/approve|reject|recall`、`POST /api/v1/approvals/batch-approve`（逐条 SAVEPOINT 隔离）；业务详情页入口保留。审批走独立**审批详情页** `/approvals/items/:bizType/:id`（非抽屉）：左栏业务完整视图（内置业务复用业务侧展示组件，如索赔单 `frontend/src/components/ClaimPaper.tsx`，需对应业务读权限；其它业务展示映射字段），右栏进度 / 操作 / 记录 / 附件；列表行点击与站内信深链均进入该页，SQL 接入业务在页内跳源系统。
- **审批链配置**：只允许操作**已注册**的 biz_type（`PUT /api/v1/approvals/configs/{biz_type}` 拒绝未注册业务，防止与其它模块配置页双写；调价单未注册、维持原入口）；支持「按角色 / 指定人员」「多条件 AND」「节点超时小时数（0=不提醒）」「启用停用（停用后不再产生新待办，在途按冻结快照继续）」。
- **超时提醒**：`app/services/scheduler/approval_timeout_reminder.py` 每小时扫描，站内信 + 企微推送当前节点审批人；Redis 按「单据+节点」24h 去重，Redis/企微不可用时降级。
- **权限域**：`approval.pending`（审批人，节点权限在引擎内二次校验）、`approval.config`（配置管理员）、`approval.business`（业务接入管理员，read/update）。
- **注意**：provider 注册表在进程内存，写配置后同步注册、本进程即时生效，应用启动时也会把启用的 SQL 业务注册进来；多实例部署时其它实例需重启。另：「审批配置」页入口按 `approval.config` 控制，业务接入管理员需同时具备 `approval.config` 才能进入页面（Tab 级再校验 `approval.business`）。

## 前端约定

- 单一 axios 实例在 `src/services/api.ts`：`baseURL: '/api/v1'`、30s 超时、token 取自 `useAuthStore`。认证/权限状态在 **Zustand** store（`src/store/auth.ts` / `permission.ts` / `theme.ts` 等）—— 不是 Redux/context。权限树只拉一次并缓存；路由→权限映射在 `permission.ts`。
- 路径别名 `@` → `src/`（`vite.config.ts` 与 `tsconfig.json` 均已配置）。
- UI：Ant Design 5 + `@ant-design/pro-components` + Tailwind。TS `strict`；unused locals/params 检查关闭（`noUnusedLocals: false`）。
- `npm run build` 是唯一前端校验；仓库**没有** `lint` / `test` / `format` 脚本，也没有 ESLint/Prettier 配置 —— 不要擅自新增。

## 测试与验证

后端有 pytest 套件（`backend/pytest.ini`，`testpaths = tests`）；前端**没有**测试运行器。

```bash
cd backend && pip install -r requirements-dev.txt   # pytest / pytest-asyncio（生产镜像不装）
python -m pytest -v                                  # 全量
python -m pytest tests/unit tests/integration -v     # 只跑供应商索赔/审批中心/网关套件
cd agents && npm install && npm test                 # runtime + gateway + 各 Agent 测试
```

- `tests/unit/` + `tests/integration/` —— 供应商索赔单 + 审批中心 + 网关 resolver/内网端点自动化测试：独立测试库 `spc_test`（conftest 自动建库 + 最小种子 + 每用例清表，**不碰开发库**），ASGI 内存客户端直打 FastAPI app，不起 uvicorn。
- **`pytest.ini` 的 `asyncio_default_fixture_loop_scope = session` / `asyncio_default_test_loop_scope = session` 是硬性前提**：全局异步引擎池跨事件循环会损坏连接，删掉这两行会让全部集成用例报 "Future attached to a different loop"。
- `tests/` 根下其余 `test_*.py`（`test_context_manager.py`、`test_cancellation.py` 等）是既有单测；`test_external_*.py` 是针对活服务的独立脚本（无 test_ 函数，pytest 只导入不执行）。
- 改审批引擎 / 索赔单 / 审批中心代码后必须跑 `python -m pytest`。
- 其余验证方式：起 uvicorn 打端点，或跑 `backend/test_*.py`、根目录 `check_*.py` / `add_*.py` 等独立脚本。

## 关键参考

- `init_database.py` —— 种子数据（角色、用户、风险规则、节点标准）与真正的迁移逻辑。
- `docs/最易出错约束点复盘-2026-07.md` —— 2026-07 会话审计：最易踩坑的约束点（int/string ID 混用、init_database 与 Alembic 漂移、ERP 同步正确性、连接池、权限），附真实报错字符串。动 models / sync / 权限前先读。
- `docs/开发约束预检清单.md` —— 按需求类型映射的可核对约束条件（CC-A1..F2），每条含触发条件 / 规则 / 通过标准 / 真实报错 / 验证命令。开工前与交付前各跑一遍适用项。

## 变更汇报格式

每次代码改动会话结束，输出如下列头的变更汇总表：

| 业务模块 | 功能 | 业务价值 / 解决的问题 | 状态 |
|---|---|---|---|
| ... | ... | ... | 已完成 |

该表必须是签退前最后一条消息的一部分，逐文件列出改动及业务影响。
