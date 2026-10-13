# SPC 系统架构基线(摸底报告)

> 产出:2026-10-13,基于 main 分支(c21bf5c)。摸底任务,不改业务代码。
> 结论均附文件/目录证据;存疑处见 §8「存疑与未读区域」。

## 0. 系统定位与规模

SPC(供应链与生产协同中台)是一个面向制造企业的**订单交付 + 物料齐套 + 生产排产协同系统**,核心形态:从金蝶 K3 ERP 中间库拉取基础数据与订单,在中台内做齐套分析、MRP、排产、异常风险扫描、审批协同,并把结果回写 ERP。

| 维度 | 数字 | 证据 |
|---|---|---|
| 后端 Python 源文件 | 424 个 / 约 87.5k 行 | `backend/app/` |
| 前端 TS/TSX 源文件 | 277 个 / 约 83.5k 行 | `frontend/src/` |
| API 端点 | 600 个(17 个路由域) | `backend/app/api/v1/__init__.py` |
| ORM 模型类 | 约 106 个 | `backend/app/models/*/` |
| Alembic 迁移文件 | 103 个(启动不执行,见 §6) | `backend/alembic/versions/` |
| 后台调度器 | 11 个 + 1 个回写 Worker | `backend/app/main.py:11-21,161-183` |
| 测试 | 后端 27 个测试文件;前端 0 | `backend/tests/`;`frontend/package.json` |
| 仓库内文档 | README、AGENTS.md、用户手册.md、docs/ 4 篇 | 仓库根、`docs/` |

## 1. 技术栈与运行形态

### 后端(`backend/`,Python 3.12)

- **Web 框架**:FastAPI 0.115.6 + uvicorn 0.34(`backend/requirements.txt:1-2`);入口 `backend/app/main.py`, lifespan 内拉起全部调度器并做权限/僵尸任务清理。
- **ORM**:SQLAlchemy 2.0.36,**双引擎**——应用走异步 asyncpg(`app/core/database.py:8-31`),`init_database.py`/Alembic/ERP 读取走同步 psycopg2/pyodbc。连接池 `pool_size=50, max_overflow=50`,服务端兜底超时(lock 15s / idle_in_txn 5min / statement 10min)。
- **数据校验**:pydantic 2.10.4 + pydantic-settings(配置)。
- **认证**:python-jose(JWT)+ passlib[bcrypt]。
- **周边**:redis 5.2.1(黑名单/权限缓存/限流/协同,10 处引用)、openpyxl + pandas(Excel 导入导出)、httpx、pyodbc 5.2.0(K3/MSSQL 直连)、openai + dashscope + tiktoken(AI)、minio 7.2.20(文件存储)。
- **闲置依赖**:`apscheduler==3.10.4` 已声明但从未使用——所有定时任务都是手写 `asyncio.create_task` + `while running: sleep` 循环(`backend/requirements.txt:19`,§6 风险 R7)。

### 前端(`frontend/`,Node 20)

- React 18.3.1 + TypeScript 5.7.2(strict)+ Vite 6 + AntD 5.22.6 + @ant-design/pro-components 2.8.1 + @ant-design/charts + TailwindCSS 3.4。
- 状态:Zustand 5(auth/permission/tabs/theme/uiPreferences/stockCheckPool/baseCondition 七个 store,`frontend/src/store/`)。
- 路由:react-router-dom 6.28 + `@remix-run/router`(为 keep-alive 页签用 `unstable_HistoryRouter`,`frontend/src/App.tsx`)。
- **双入口**:`index.html`(桌面端)+ `mobile.html`(antd-mobile H5,盘点扫码场景),`vite.config.ts` rollupOptions.input 两入口、dev 中间件改写 `/m/*`。
- 其它:xlsx(前端解析 Excel)、react-flow-builder(审批流设计器)、html5-qrcode / qrcode.react(扫码)、react-markdown(AI 对话)、docx-preview。
- **脚本只有 dev/build/preview**——`npm run build`(= `tsc -b && vite build`)是唯一校验,无 lint/test/format 配置(`frontend/package.json:6-10`)。

### 数据与基础设施

PostgreSQL 15(主库)+ Redis 7(密码模式)+ MinIO(S3 兼容文件存储,`STORAGE_BACKEND=local|s3` 双模,`backend/app/core/storage/`)。

### 部署形态(多服务器 Windows 本机 + Docker)

- 三套 compose:本地开发 `docker-compose.yml`(backend :8000 / frontend :3000)、生产全套 `docker-compose-prod.yml`(自带 postgres/redis/minio,backend :18085 / frontend :18084,**容器启动命令含 `python init_database.py`** 即每次启动自动迁移)、纯应用 `docker-compose-app.yml`(app 角色只跑应用连主库)。
- 远程部署:PowerShell 脚本 `scripts/deploy-remote.ps1` + `scripts/deploy-config.ps1` 的 `$DEPLOY_SERVERS`(main=full 角色、mac-server=app 角色),版本回退 `scripts/manage-version.ps1`。
- 前端容器内置 nginx(`frontend/nginx.conf` + 根 `nginx.conf`):SPA fallback、`/m/` 移动端入口、`/api/` 与 `/uploads/` 反代 backend,上传上限 20m。
- **无任何 CI 配置**(无 `.github/`、`.gitee/`、Jenkinsfile)——构建校验只靠本地手跑。

### 附属系统

`mcp-company-control/`:独立 Python MCP Server(官方 mcp SDK 2.x,stdio/streamable-http),把中台只读能力以 MCP Tool 形式接入 AEOS Hub,全部 READ_ONLY(`mcp-company-control/README.md`)。

## 2. 仓库与模块结构

### 顶层布局

```
spc/
├── backend/          # FastAPI 后端(见下)
├── frontend/         # React 前端(见下)
├── mcp-company-control/  # 独立 MCP 只读适配器
├── docs/             # 排产规划、模块说明、调价单设计等 4 篇 + prototype/superpowers
├── scripts/          # PowerShell 远程部署脚本
├── prototype/        # global-search.html 原型
├── 订单管控表/        # 业务 CSV 台账(21 个文件,业务资料混入代码仓库)
├── docker-compose*.yml / nginx.conf / .env.example / .env.app1.example
├── AGENTS.md         # AI 会话工作守则(重要,但有漂移,见 §6 R3)
├── README.md / 用户手册.md
```

### 后端分层(`backend/app/`)

```
api/v1/   路由层,17 个域,600 端点,全部挂 /api/v1 下(api/v1/__init__.py 汇总)
schemas/  pydantic 请求/响应模型(按域分目录)
services/ 业务逻辑层(按域分目录,系统的重心,约 39.7k 行)
models/   SQLAlchemy 模型(按域分目录,经 models/__init__.py 显式注册进 Base.metadata)
core/     横切设施:config / database / security / dependencies(认证)/ permissions /
          permission_registry / permission_cache / token_blacklist / redis_client /
          audit / supplier_scope / storage(local+S3)
```

**API 域与端点数**(grep 各 router 装饰器统计):basicdata 186、material 110、production 90、external 36、purchase 30、order 23、mrp 20、approval 18、exception 17、common 16、quality 13、dashboard 11、writeback 10、system 8、rules 7、assistant 7;`masterdata/` 只有空 `__init__.py`(占位未用)。

**业务中心 ↔ 前端页面组对应**:订单交付(OrderDelivery)、物料齐套(MaterialCenter,最大 51 个页面文件)、生产协同(ProductionCenter)、异常与质量(ExceptionCenter)、规则配置(RulesCenter)、基础数据(BasicDataCenter,36 个文件)、审批中心(ApprovalCenter,26 个)、品质索赔(QualityCenter)、调价(Purchase/PriceChange)、驾驶舱(Dashboard)、备份(SystemCenter)、通知/个人/分享等单页(`frontend/src/pages/`)。

### 依赖方向(模块边界)

```mermaid
title="SPC 后端依赖方向(箭头 = import)"
flowchart TD
    api["api/v1 各域路由"] --> schemas
    api --> svc["services 各域"]
    svc --> models["models 各域"]
    svc --> core["core(config/db/auth/permissions/storage/redis)"]
    models --> core
    subgraph foundation["底座域"]
        basicdata["basicdata(ERP 镜像+用户权限+同步)"]
        common["common(审批引擎+单据+导出)"]
    end
    material --> basicdata
    mrp --> material
    order --> material
    production --> order
    dashboard --> exception
    quality --> common
    material --> common
    purchase --> common
    assistant["assistant/ai(顶层,读一切)"] --> material & order & production & basicdata
    sched["scheduler/*(编排层)"] --> production & mrp & backup & notification
    svc --> notification
```

实测结论(基于全量 import 扫描):

- 总体单向清晰:`api → services → models → core`;**basicdata 与 common 是底座**,被所有业务域依赖;assistant/AI 与 dashboard 在顶层只读聚合;scheduler 是编排层。
- **无模块级循环导入**。两个潜伏环靠**函数内惰性导入**人为拆开,改代码时别把它引进模块顶层:
  - `services/production/upph_formula_config_service.py:146` 惰性导入 `ProductProcessCapacitySyncService`,而后者在 `product_process_capacity_sync_service.py:19` 顶层反向导入前者——真实 `a ⇄ b` 环,单向拆弹;
  - `services/production/schedule_plan_cascading_service.py:473,527-528` 惰性导入 `capacity_slot_service` / `config_service`(防御性,对方不反导入)。
- **域级双向耦合(非 import 环)**:order 域引 material 的模型,material 域的两个服务(`kit_analysis_service.py:36`、`stock_check_service.py:23`)反过来引 order 域的 `order_materials_service`。新增功能时 order/material 之间的调用要格外小心边界。

### 前端结构(`frontend/src/`)

```
pages/        200 个文件,17 个业务组(pages/<Center>/<Module>/index.tsx 惯例)
mobile/       20 个文件,第二 SPA(antd-mobile):登录/工作台/盘点扫码
components/   29 个共享组件(ClaimPaper、ApprovalChainEditor、PermButton、GlobalSearch、Assistant…)
layouts/      MainLayout.tsx(1081 行,菜单+权限过滤)+ AppTabs.tsx(keep-alive 页签)
services/     api.ts(886 行,单一 axios 实例 + ~30 个 API 对象)+ 5 个域拆分文件 + SSE 流
store/        7 个 Zustand store
hooks/        useAntTableQuery(服务端分页表格)/useExport/useStockCheckSync 等 7 个
router/       contentRoutes.tsx(约 100 条扁平路由)
```

路由守卫三层:`PrivateRoute`(token)→ `ShareRouteGuard`(分享用户锁定路径)→ MainLayout 页面级权限(`getRequiredPermission`,菜单由后端权限树数据驱动过滤)。**无任何 React.lazy/代码分割**,所有页面静态导入进单一 bundle(`src/router/contentRoutes.tsx`)。

## 3. 数据模型与读写路径

### 实体分布(约 106 个模型类,`backend/app/models/<domain>/`)

| 域 | 模型(表) | 说明 |
|---|---|---|
| basicdata(31 文件/36 类) | sys_user/sys_role、scm_employee/organization/material/bom/inventory/process…、sync_log、sync_sql_config、writeback_queue/log/sql_config、data_supply_*、share_link、backup_*、announcement/notification、audit_log、file_asset | **ERP 镜像 + 平台设施**,最大域 |
| material(24 类) | purchase_order/requisition(+line/approval_log)、subcontract_order(+detail)、receipt_batch、material_demand/issue、binding、kitting_run/result/shortage、scm_inventory_check*(盘点族)、supplier_message、transfer_order、mrp_plan_order | 齐套/采购/盘点 |
| order(4 类) | sale_order(+line)、run_order、eta_update | 订单交付 |
| production(17 类) | production_schedule_plan、capacity_slot、base_condition、production_daily_report、workshop_daily_report(+3 子表)、labor_price_audit、task_order、sale_order_line_change_log、upph 相关 | 排产/产能/日报 |
| mrp(7 类) | mrp_run/scheme/bucket/parameter/substitute/suggestion/exception | 2026-09 新增 MRP 域 |
| common(6 类) | approval_instance/task/record/business、business_document(+version) | 审批中心 + 业务单据 |
| quality(2)/purchase(6)/exception(2)/rules(2) | supplier_claim 族、price_change 族、risk_issue、quality_issue、risk_rule、node_standard | |
| masterdata/meeting/npi | 仅空 `__init__.py` 或占位 docstring | 未落地的域 |

### 双 schema 机制(改表前必读)

1. **`backend/init_database.py`(2523 行)是运行时事实来源**:`Base.metadata.create_all` + 手工维护的 `migrate_columns` 字典跑 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`/删列 + 十余个 `migrate_*`/`backfill_*`/`seed_*` 幂等函数;生产 compose 每次容器启动都执行。**只写 Alembic 迁移的新列,容器重启后不会出现**。
2. Alembic(103 个迁移文件)存在但启动不跑,仅手动;`alembic.ini:5` 的 DB URL 是占位值,与 `.env` 漂移。
3. **加列正确姿势**:SQLAlchemy model 与 `init_database.py` 的 `migrate_columns[table]` 同步加(仓库主流做法)。新模型模块必须在 `app/models/__init__.py`(或经包 `__init__`)被 import,否则 `create_all` 看不到。

### 主读写路径

- **业务读写**:端点 `Depends(get_db())` 拿异步 session——**成功自动 commit、异常自动 rollback**,端点内不要手动 commit(`app/core/database.py:44-51`);纯只读端点用 `get_read_only_db()` 跳过 commit 省网络往返。
- **ERP 拉取(定时)**:`services/basicdata/sync_scheduler.py` 60 秒主循环 → 逐条读 `sync_sql_config` 表(同步 SQL 与字段映射**存数据库、运行时可编辑**)→ `erp_sync_service.py`(3405 行)在独立线程经 pyodbc 查 K3 中间库 → 预载本地主键做 diff → `_bulk_upsert`。**守卫:ERP 同步只覆盖 `data_source='erp'` 行,永不碰 `manual`/`excel` 行**。
- **ERP 回写(队列)**:业务服务 `writeback_service.enqueue_writeback` 入 `writeback_queue`(按 pending 去重)→ `writeback_worker.py` 轮询(`writeback_poll_interval`,默认 5s)认领批次 → 按 `writeback_type` 从 `writeback_sql_config` 取 SQL 模板渲染执行(走**独立的 ERP 写引擎** `erp_db_url_write`,K3 写账套 `K3_WRITE_DB` 可与读账套分离)→ 写 `writeback_log`;失败退避重试,超时回收。
- **文件**:本地磁盘或 MinIO(`app/core/storage/`,S3 模式含元数据文件名百分号编码,见最近提交 c21bf5c)。
- **备份**:`services/backup/backup_service.py` pg_dump/restore,恢复期间中间件挡业务流量 503(`app/main.py:234-244`)。

## 4. 对外契约

### API 路由(600 端点,全部 `/api/v1` 前缀)

分组与挂载见 `backend/app/api/v1/__init__.py`(域与数量见 §2)。几个特殊面:

- `external/`(36 端点):**对外数据供给接口**,直挂主应用但 `include_in_schema=False`(内部 /docs 不混入),有专属 OpenAPI 文档路由。18 个 endpoint 模块(orders/bom/inventory/production/quality/…),按 `endpoint_code` 注册(`external/registry.py`)。
- `assistant/`(7 端点):AI 智能助手,SSE 流式对话。
- `/health`(根路径,无鉴权):健康检查(`app/main.py:256-258`)。

### 响应信封(客户端强制约定)

成功端点必须返回 `{code, message, data}`(`app/schemas/common.py` 的 `ResponseModel`/`PageResult`);前端 axios 拦截器把 `code !== 0` 判为失败——**裸 list/dict 即使 HTTP 200 也被判失败**(`frontend/src/services/api.ts:47-70`)。分页统一 `{total, page, page_size, items, stats?}`。

### 鉴权体系(四套并行)

1. **用户 JWT**(`basicdata/auth/login`,form-urlencoded,employee|supplier 双通道;企微扫码/OAuth 登录同在此):token 携带 `login_version` + `jti` 两层失效——重登 bump `sys_user.login_version`,登出拉黑 jti(Redis `app/core/token_blacklist.py`);`app/core/dependencies.py` 的 `get_current_user` 统一校验,强制登出响应带 `X-Force-Logout: true`。
2. **权限模型**:角色 → `permissions = {resource: [actions]}` 字典;`permission_registry` 每次启动同步权限定义到 DB;页面级由 `PermissionChecker(resource, action)`(`app/core/security.py:177`)与前端权限树双侧控制。
3. **分享 token**:JWT 内 `share: true`,绕过权限与 login_version,只能访问被分享路由(`get_current_user_or_share`)。
4. **对外 API Key**:签名(`X-App-Key` + `X-Timestamp` + `X-Signature`)+ IP 白名单 + 每分钟限流,`external/deps.py` 的 `external_auth(endpoint_code)`。

## 5. 既有约定

- **命名**:后端 snake_case 按域分目录(`api/v1/<domain>/`、`services/<domain>/`、`models/<domain>/` 三层同构);前端页面 `pages/<Center>/<Module>/index.tsx`、PascalCase 组件。中英混合命名(文档/注释/提交信息中文,代码标识符英文)。
- **错误处理**:HTTPException(510 处)+ ResponseModel 信封;前端拦截器统一 toast + 401 强制登出流程。后端错误文案面向用户为中文。
- **日志**:标准 `logging.getLogger`(65 处),关键链路(ERP 同步、调度器、回写)有结构化中文日志;**残留 1 处调试输出**:`erp_sync_service.py:760` 的 `print(f"ERP数据:{rows}")` 会把整批 ERP 行打到 stdout(§6 R9)。
- **配置**:`app/core/config.py` 单一 Settings(pydantic-settings),`_ENV_FILES` 四级加载(仓库根 .env.local → .env → CWD .env.local → .env,后载覆盖),`get_settings()` 带 `@lru_cache`(改 env 必须重启);compose 只显式转发 environment 列表里的变量,`.env.example` 模板对「直连生效」变量有逐项标注。
- **JSON 序列化**:`main.py` 的 `SafeJSONResponse` 覆盖默认响应类,容忍 Decimal/datetime/非 UTF-8 字符串——**不要绕过它**。
- **代码整洁守则**:AGENTS.md 有强约束的防重复守则(先查再写、DRY+Rule of Three、函数 ≤40 行、最小改动、禁调试残留、交付自查清单),以及交付时输出「业务模块/功能/价值/状态」变更汇总表。
- **测试**:后端 pytest(`backend/pytest.ini`,testpaths=tests),`tests/unit`(13 文件,审批/MRP/备份/通知)+ `tests/integration`(14 文件,ASGI 内存客户端直打 FastAPI,独立 spc_test 库,conftest 自动建库+清表);**`pytest.ini` 的 session 级 loop scope 两行是硬性前提勿删**。`tests/` 根下 `test_external_*.py` 是打活服务的独立脚本(pytest 只导入不执行)。**前端零测试、零 lint**。改审批引擎/索赔单/审批中心后必须跑 `python -m pytest`。

## 6. 风险点与技术债(按影响排序)

| # | 风险 | 证据 | 影响 |
|---|---|---|---|
| R1 | **单体巨文件**:后端最大 `api/v1/production/schedule_plans.py` **7097 行**(单文件承载整个排产模块路由);`services/material/stock_check_service.py` 4002 行、`services/basicdata/erp_sync_service.py` 3405 行(17 个 sync_* 方法一类);前端 5 个 2000+ 行页面(SchedulePlans 2567 / DataSupply 2321 / OrderList 2303 / StockCheck Workbench 2290 / UserManagement 2037),全库约 25 个 900+ 行文件 | wc -l 实测 | 改动冲突面大、评审困难、回归风险集中;新功能尽量新文件,别往巨文件里加 |
| R2 | **双 schema 机制漂移**:init_database.py(手工 migrate_columns)与 Alembic(103 迁移,启动不跑,alembic.ini URL 为占位符)长期并存 | `backend/init_database.py:127`、`backend/alembic/versions/`(103 文件)、`backend/alembic.ini:5` | 只改一边的加列在生产消失;新表/新列必须 model+init_database 双写 |
| R3 | **文档漂移 + .gitignore 排除 docs**:AGENTS.md 引用的 `docs/最易出错约束点复盘-2026-07.md`、`docs/开发约束预检清单.md`、`docs/备份管理设计-2026-09.md` 在 main 分支均不存在——根因是 `.gitignore:68-73` 把 `docs/` 与 `*.md` 整体排除(「本机笔记,不提交」,仅白名单 AGENTS/README/CODE_WIKI 等),这些文档只存在于开发机;AGENTS.md「七个后台任务」实为 11 个调度器+1 Worker,「约 50 个迁移文件」实为 103 | `.gitignore:68-73`;`app/main.py:11-21`;find 实测 | 文档与代码不同步是常态:仓库内文档可能滞后或缺失,关键约束以代码与本报告为准;**新文档入库必须 `git add -f`**(已有 53 个 docs/**/*.md 靠此路径被追踪,本报告同) |
| R4 | **后台任务全部进程内 asyncio 循环**:11 个调度器随 uvicorn 进程跑,无独立 worker/消息队列;多实例部署时同一调度会在每个实例各跑一份(仅同步任务按 server_id 清僵尸有隔离意识);审批 provider 注册表在进程内存,写配置后其它实例需重启 | `app/main.py:161-183`;AGENTS.md 审批节自述 | 水平扩展受限、单点;扩实例前必须先解决任务去重 |
| R5 | **order ⇄ material 域双向耦合 + 2 个惰性导入拆环**:material 服务调 order 服务,production 域内有真实 a⇄b import 环靠函数内导入压住 | `services/material/kit_analysis_service.py:36`、`stock_check_service.py:23`;`upph_formula_config_service.py:146` ⇄ `product_process_capacity_sync_service.py:19` | 重构/移动模块时易爆循环导入;顶层 import 这些服务前先想清楚方向 |
| R6 | **无 CI**:仓库无任何 CI 配置(无 .github/.gitee/Jenkinsfile),构建与测试校验全靠本地手跑 | ls 实测 | 回归靠自觉;AGENTS.md 的「交付前必跑」无机器强制 |
| R7 | **前端无 lint/test/代码分割**:唯一校验 npm run build;无 React.lazy,全部页面进单一 bundle | `frontend/package.json:6-10`;`src/router/contentRoutes.tsx` 静态导入 | 前端质量裸奔;首屏体积随页面数线性膨胀 |
| R8 | **安全默认值**:`SECRET_KEY` 默认 "your-secret-key-change-in-production"、`ERP_SYNC_DEFAULT_PASSWORD="admin123"`、默认账号密码 admin123(AGENTS.md 明文列出) | `app/core/config.py:36,56`;AGENTS.md | 生产必须确认已覆盖;.env 管理纪律是唯一防线 |
| R9 | **调试残留**:`erp_sync_service.py:760` `print(f"ERP数据:{rows}")` 在同步主路径把整批 ERP 行打 stdout | 该行实测 | 日志噪音 + 业务数据进容器日志;顺手清理的低垂果实 |
| R10 | **空占位域**:api/models/services 三层的 masterdata、meeting、npi 目录均无实现;api/v1/__init__.py import 了 masterdata 但未挂载 | 目录实测 | 域拆分未完成;新功能别误放进占位目录 |
| R11 | **业务资料混入仓库**:根目录 `订单管控表/`(21 个 CSV 业务台账)、`prototype/` | 目录实测 | 仓库边界模糊;非代码资产无版本规范 |
| R12 | **杂项**:`apscheduler` 依赖闲置(requirements.txt:19);根 `nginx.conf` 中文注释乱码(编码不一致);`frontend/src/services/api.ts` 886 行集中了 ~30 个 API 对象 | 各处实测 | 小,但拉低一致性 |

## 7. 既有约定速查(新功能对照)

1. 新端点:进对应域目录 `api/v1/<domain>/`,路由在 `api/v1/__init__.py` 挂载;响应必须包 `ResponseModel` 信封;读库用 `get_db()`(自动 commit)或 `get_read_only_db()`(只读)。
2. 新表/新列:model 放 `models/<domain>/` 并在 `models/__init__.py` 注册;**同时**登记 `init_database.py`(create_all 自动覆盖全新表;加列要进 `migrate_columns`)。
3. 前端新页面:`pages/<Center>/<Module>/index.tsx`,路由进 `contentRoutes.tsx`,菜单靠权限树自动出现;API 调用加进 `services/api.ts` 或对应域拆分文件。
4. 权限:新资源先在 `permission_registry` 注册;角色基础权限增量加到 `app/core/permissions.py` 的 `ROLE_PERMISSION_ADDITIONS`(不要恢复覆盖式 seed)。
5. 涉及审批:builtin 业务在 `services/common/approval_providers.py` 注册 provider;SQL 零开发接入走审批配置页。
6. 涉及 ERP:同步只动 `data_source='erp'` 行;回写一律走 `enqueue_writeback` 队列,不直连写。
7. 验证:后端 `python -m pytest`(涉审批/索赔/MRP 必跑);前端 `npm run build`;汇报用 AGENTS.md 的变更汇总表格式。

## 8. 存疑与未读区域

- **未深读的巨文件**:`api/v1/production/schedule_plans.py`(7097 行)与 `stock_check_service.py`(4002 行)只做了结构定位,未逐行读;排产算法细节(冻结区/级联/仿真)只从服务文件名与调用关系推断。
- **数据库实际状态未连库验证**:表数量、索引、数据量均来自代码与 init_database.py,未连生产/开发库核对。
- **K3 中间库表结构**在仓库内不可见(SQL 存在 sync_sql_config 表里,不在代码里),ERP 侧字段映射只能看 service 代码。
- `docs/superpowers/`、`docs/prototype/` 只确认存在,未逐篇读。
- 分支差异:main 之外有 cqx、whz、应用多开页签调整 三个分支,未对比其与 main 的偏离。
- 多实例部署的真实拓扑(几台、角色分配)只从 deploy-config.ps1 的两个服务器条目推断,未实际核对线上。

## 9. 新功能开发时先看哪几节

1. **§2 依赖方向** —— 决定代码放哪个域、能 import 谁;特别注意 R5 的双向耦合与惰性导入拆环点。
2. **§3 双 schema 机制 + 读写路径** —— 动表前必读,加列双写是硬规则。
3. **§4 响应信封与鉴权** —— 新端点的契约红线(裸 dict 会被前端判失败)。
4. **§7 约定速查** —— 按步骤对照落地。
5. **§6 风险表** —— 避开 R1 巨文件(开新文件)、R6 无 CI(交付前手跑测试与 build)。
6. 仓库根 **AGENTS.md** —— 代码整洁守则与命令速查(注意其文档引用有漂移,以本报告 §6 R3 为准)。
