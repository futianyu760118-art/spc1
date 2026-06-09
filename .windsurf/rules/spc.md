---
trigger: always
---

# SPC-v2 供应链与生产协同中台 — 项目规则

> 本规则与《供应链运营协同中台建设计划书V2》保持一致，代码按 **9 大业务中心** 组织。

## 1. 项目概述

供应链与生产协同中台，覆盖 9 大业务中心：

1. **供应链驾驶舱（Dashboard）** — 今日总览 / 14 天滚动风险 / 订单风险分布 / 闭环达成看板
2. **订单交付中心（OrderDelivery）** — 订单行、ETA、交付里程碑
3. **物料齐套中心（MaterialCenter）** — 物料需求、采购订单、绑定、到货
4. **异常与质量中心（ExceptionCenter）** — 风险扫描、异常台账
5. **生产协同中心（ProductionCenter）** — 占位
6. **会议与任务中心（MeetingCenter）** — 占位
7. **新品 / NPI 项目中心（NPICenter）** — 占位
8. **规则配置中心（RulesCenter）** — 风险规则、试点、同步 SQL 等
9. **主数据与集成中心（MasterDataCenter）** — 认证、用户、审计、导入导出、ERP 同步

## 2. 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + Ant Design 5 + Ant Design Pro Components + TailwindCSS 3 + Vite 6 |
| 状态管理 | Zustand 5（持久化到 localStorage） |
| 路由 | React Router DOM 6 |
| HTTP 客户端 | Axios（baseURL `/api/v1`，Vite proxy → 后端 8000） |
| 图表 | @ant-design/charts (G2Plot) |
| 后端 | Python FastAPI 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0（异步 asyncpg + 同步 psycopg2）+ Alembic |
| 数据库 | PostgreSQL 15（JSONB 扩展字段） |
| 认证 | JWT (python-jose) + bcrypt + RBAC（admin / operator / viewer） |
| 定时任务 | APScheduler 3.10（lifespan 挂载） |
| 文件处理 | openpyxl + pandas |
| ERP 对接 | pyodbc（SQL Server 中间库只读）+ httpx |
| 部署 | Docker Compose（前端 Nginx:80 → 3000，后端 Uvicorn:8000） |

> 注：当前代码未实际使用 Redis / Celery，若引入请同步更新本规则。

## 3. 目录结构约定

### 3.1 后端 `backend/app/`（按 9 模块分包）

```
app/
├── main.py                       # FastAPI 入口，lifespan 管理 scheduler
├── core/                         # config / database / security / dependencies
├── models/                       # SQLAlchemy 模型，按模块分包
│   ├── order/ material/ exception/ rules/
│   ├── masterdata/ dashboard/ production/ meeting/ npi/
│   └── __init__.py               # 显式 import 所有模型，供 Alembic 识别
├── schemas/                      # Pydantic v2，按模块分包；common.py 放通用 ResponseModel/PageResult
├── services/                     # 业务逻辑，按模块分包；Service 类注入 AsyncSession
├── api/v1/                       # APIRouter，按模块分包
│   └── __init__.py               # 汇总 include_router，统一前缀见 §3.3
└── scripts/                      # 独立脚本
alembic/                          # 迁移脚本
```

### 3.2 前端 `frontend/src/`（按 9 模块分包）

```
src/
├── main.tsx                      # ConfigProvider(zhCN) + Indigo 主题
├── App.tsx                       # BrowserRouter + PrivateRoute
├── layouts/MainLayout.tsx        # 9 模块层级菜单 + 面包屑
├── pages/
│   ├── Dashboard/                # 4 视图 tab（今日总览 / 14天滚动 / 风险分布 / 闭环达成）
│   ├── OrderDelivery/            # OrderList / OrderDetail / CheckpointList
│   ├── MaterialCenter/           # MaterialKit / PurchaseOrders / ETAUpdate
│   ├── ExceptionCenter/          # IssueLedger
│   ├── ProductionCenter/         # 占位
│   ├── MeetingCenter/            # 占位
│   ├── NPICenter/                # 占位
│   ├── RulesCenter/              # Settings（规则 / 试点 / 同步SQL / 字段映射）
│   ├── MasterDataCenter/         # DataIntegration（导入 / ERP 同步 / 用户 / 审计）
│   └── Login.tsx
├── services/api.ts               # Axios 实例 + 按模块分组的 API 对象
├── store/auth.ts                 # Zustand auth store
├── components/                   # 公共组件（RiskBadge、StatusTag 等）
├── hooks/                        # 自定义 hooks
└── utils/                        # 工具函数
```

### 3.3 API 前缀总览（`/api/v1` 为全局前缀）

| 模块 | 路由前缀 |
|---|---|
| 供应链驾驶舱 | `/dashboard` |
| 订单交付中心 | `/orders`、`/orders/eta` |
| 物料齐套中心 | `/materials` |
| 生产协同中心 | `/production`（占位） |
| 异常与质量中心 | `/exceptions`、`/exceptions/risk` |
| 会议与任务中心 | `/meetings`（占位） |
| 新品 / NPI | `/npi`（占位） |
| 规则配置中心 | `/rules` |
| 主数据与集成中心 | `/masterdata/auth`、`/masterdata/users`、`/masterdata/audit`、`/masterdata/import-export`、`/masterdata/sync`、`/masterdata/sync-sql` |

## 4. 后端编码规范

### 4.1 模型层 (`models/<module>/`)
- 继承 `app.core.database.Base`（DeclarativeBase）
- 使用 SQLAlchemy 2.0 `Mapped[T]` + `mapped_column()`
- 时间字段统一 `server_default=func.now()`，更新字段加 `onupdate=func.now()`
- 扩展字段使用 `JSONB`
- 表名 snake_case（如 `sale_order`、`material_demand`）
- **新增模型必须在 `app/models/__init__.py` 显式 import 并加入 `__all__`**，否则 Alembic `autogenerate` 不会识别

### 4.2 Schema 层 (`schemas/<module>/`)
- Pydantic v2，`model_config = {"from_attributes": True}`
- 通用：`schemas/common.py` 的 `ResponseModel[T]`、`PageResult[T]`
- 命名：`XxxBase` → `XxxCreate` → `XxxUpdate` → `XxxOut`

### 4.3 API 层 (`api/v1/<module>/`)
- 每个子模块内可按子域拆分（如 `order/routes.py` + `order/eta.py`），在模块 `__init__.py` 暴露 `router` 或 `xxx_router`
- 在 `api/v1/__init__.py` 中注册并设置中文 `tags`
- 认证：`Depends(get_current_user)`；权限：`Depends(RoleChecker(["admin","operator"]))`
- 统一响应：`ResponseModel(data=...)`
- 分页参数：`page: int = Query(1, ge=1)`, `page_size: int = Query(20, ge=1, le=100)`

### 4.4 服务层 (`services/<module>/`)
- `class XxxService: def __init__(self, db: AsyncSession)`
- 复杂逻辑（绑定引擎、风险计算、ERP 同步、导入导出）封装为 Service
- 事务由 `get_db()` 统一 commit / rollback

### 4.5 配置与环境
- `pydantic-settings` + `.env`，`@lru_cache get_settings()`
- API 前缀 `/api/v1`
- CORS 允许 `localhost:3000` / `localhost:5173`

### 4.6 数据库迁移
- Alembic 版本目录：`backend/alembic/versions/`
- `alembic/env.py` 使用同步 `DATABASE_URL_SYNC`
- 流程：在 `models/__init__.py` 注册新模型 → `alembic revision --autogenerate -m "..."` → `alembic upgrade head`

## 5. 前端编码规范

### 5.1 路由与布局
- 路由定义于 `App.tsx`，`PrivateRoute` 包裹认证页面
- `MainLayout` 按 9 模块层级菜单 + 面包屑
- 路径别名 `@` → `src/`

### 5.2 API 调用（`services/api.ts`）
- Axios 实例 `baseURL: /api/v1`，请求拦截器注入 Bearer Token
- 响应拦截器：`data.code !== 0` 抛错；401 自动登出跳转
- 按模块导出 API 对象：
  - `dashboardApi`（驾驶舱，含 4 视图 API）
  - `orderApi`（订单交付）、`etaApi`（ETA，`/orders/eta/...`）
  - `poApi`（物料齐套的采购订单，打到 `/materials/...`）
  - `issueApi` / `riskApi`（异常与质量，打到 `/exceptions/...`）
  - `ruleApi`（规则配置）、`pilotApi`（试点）
  - `authApi` / `userApi` / `auditApi` / `importExportApi`（主数据与集成，打到 `/masterdata/...`）
- **命名约定**：对象名按业务习惯保留历史命名，**URL 路径必须遵循 §3.3 的 9 模块前缀**

### 5.3 状态管理
- Zustand store 放 `store/`
- `auth.ts` 持久化 token / user 到 localStorage

### 5.4 UI 风格
- 主色 Indigo `#6366f1`
- 圆角：Button/Input/Select 10px；Table/Card/Modal 12–16px
- Ant Design `zhCN`
- TailwindCSS 仅辅助布局，不覆盖 Ant Design 组件样式
- 侧边栏渐变 `linear-gradient(180deg, #1e1b4b, #312e81)`
- Glassmorphism：半透明白 `rgba(255,255,255,.55)`

### 5.5 字体大小统一规范
- **全局配置**：使用 CSS 变量 `--font-size-scale`（默认值 1），通过 `useThemeStore` 管理
- **Ant Design 组件**：自动继承全局配置，无需额外处理（`ConfigProvider` 已设置 `fontSize: 14 * fontSizeScale`）
- **自定义样式**：在 `index.css` 或组件样式中使用 `calc(base_size * var(--font-size-scale))` 格式
- **内联样式**：使用 `style={{ fontSize: 'calc(1rem * var(--font-size-scale))' }}`
- **TailwindCSS**：配合 CSS 变量使用，避免硬编码固定字体大小
- **禁止**：在页面组件中硬编码固定字体大小值（如 `fontSize: 14px`），必须使用 CSS 变量实现可缩放
- **动态调整**：用户可通过 `FontSizeSetting` 组件调整全局缩放比例，所有使用该变量的页面会自动同步

### 5.6 组件编写
- 函数式组件 + hooks
- 页面目录 `index.tsx` 为入口，子组件放 `components/`
- 表格优先 ProTable，表单优先 ProForm，日期用 dayjs

## 6. 数据库核心表

| 模块 | 表名 | 关键字段 |
|---|---|---|
| 订单交付 | `sale_order` / `sale_order_line` | order_no + line_no (UK), risk_level, status |
| 订单交付 | `eta_update` | po_no, old_eta, new_eta, update_reason |
| 物料齐套 | `material_demand` | order_no, material_code, shortage_flag |
| 物料齐套 | `purchase_order` | po_no (UK), eta, original_eta, po_status |
| 物料齐套 | `order_material_po_binding` | order_no, material_code, po_no, bind_status |
| 物料齐套 | `receipt_batch` | receipt_no, po_no, quality_status |
| 异常与质量 | `risk_issue` | issue_no (UK), issue_type, risk_level, status |
| 规则配置 | `risk_rule` | rule_code (UK), condition_json (JSONB) |
| 主数据与集成 | `sys_user` / `sys_role` | role_code: admin/operator/viewer |
| 主数据与集成 | `audit_log` | table_name, record_id, action, old/new_value |
| 主数据与集成 | `field_mapping` | 导入字段映射 |
| 主数据与集成 | `sync_sql_config` | ERP 同步 SQL 模板 |
| 规则配置 | `pilot_config` | config_type, config_value |

## 7. 业务领域术语

- **风险灯号**：red（高）/ yellow（中）/ green（正常）
- **绑定引擎**：按 `material_code` 将物料需求匹配到 PO，自动分配数量
- **欠料**：`shortage_flag=true`，物料需求未被 PO 完全覆盖
- **ETA**：采购订单预计到货日期
- **风险类型**：`missing_po`（漏下单）/ `eta_delay`（ETA 延期）/ `long_lead`（长周期）/ `holiday_risk`（假期风险）
- **PO 状态流**：placed → accepted → in_production → shipped → received
- **订单状态**：open → in_progress → completed / cancelled
- **驾驶舱 4 视图**：今日总览 / 14 天滚动风险 / 订单风险分布 / 闭环达成

## 8. 开发注意事项

- 新增 API 路由：在对应模块 `api/v1/<module>/__init__.py` 暴露 router，再到 `api/v1/__init__.py` 注册 **并带中文 tag**
- 新增模型：在 `app/models/__init__.py` 显式 import → Alembic autogenerate → upgrade head
- 新增前端页面：必须落在对应模块目录下（9 大中心之一），并在 `App.tsx` 与 `MainLayout` 菜单同步
- 所有写操作需考虑审计日志（`audit_log`）
- 占位模块（`production / meeting / npi`）：仅保留骨架，不新增业务逻辑，除非计划书推进到对应阶段
- 后端启动：`uvicorn app.main:app --reload --port 8000`（在 `backend/`）
- 前端启动：`npm run dev`（在 `frontend/`），通过 Vite proxy 代理到 `http://localhost:8000`
- 错误提示使用中文（如"无效的认证凭据"、"权限不足"）

## 9. 表格筛选与排序规范（服务端模式）

所有数据表格的筛选和排序必须走**服务端**，禁止客户端 `onFilter` / `sorter` 函数。

### 9.1 后端 API 规范

- **排序**：接收 `sort_by: Optional[str]` + `sort_order: Optional[str]`（`asc` / `desc`），用白名单映射列名到 ORM 列对象，动态构建 `order_by`；无排序时使用默认排序
- **筛选**：多值筛选参数接受逗号分隔字符串（如 `po_status=pending,overdue`），后端 `split(',')` 后用 `or_(*conditions)` 组合
- **分页**：`page` + `page_size`，返回 `PageResult[T]` 含 `items` + `total`

```python
# 排序白名单示例
SORTABLE_COLUMNS = {
    'po_qty': PurchaseOrder.po_qty,
    'eta': PurchaseOrder.eta,
}
# 动态排序
if sort_by in SORTABLE_COLUMNS:
    col = SORTABLE_COLUMNS[sort_by]
    order_clauses.append(col.desc().nullslast() if sort_order == 'desc' else col.asc().nullslast())

# 多值筛选示例
status_list = [s.strip() for s in po_status.split(',')]
conditions = []
for s in status_list:
    if s == 'overdue': conditions.append(...)
base.append(or_(*conditions))
```

### 9.2 前端 Table 规范

- **排序**：列定义用 `sorter: true`（仅标记可排序），不写客户端排序函数
- **筛选**：列定义用 `filters` + `filteredValue`，**禁止** `onFilter`；筛选值存入 state，由 `load()` 传给后端
- **多值筛选**：state 用 `string[]`，API 调用时 `.join(',')` 传给后端
- **Table onChange**：统一处理分页、筛选、排序三件事，**禁止** 在 pagination 中单独设 `onChange`

```tsx
// 正确模式
const [filters, setFilters] = useState({ po_status: [] as string[] })
const [sortBy, setSortBy] = useState('')
const [sortOrder, setSortOrder] = useState('')

// load() 传参
...(filters.po_status.length ? { po_status: filters.po_status.join(',') } : {}),
...(sortBy ? { sort_by: sortBy, sort_order: sortOrder } : {}),

// 列定义
{ dataIndex: 'po_status', sorter: true,  // 不写 sorter 函数
  filters: [...], filteredValue: filters.po_status.length ? filters.po_status : null,  // 不写 onFilter
}

// Table onChange 统一处理
onChange={(pagination, tableFilters, sorter: any) => {
  setPage(pagination.current || 1)
  setPageSize(pagination.pageSize || 20)
  const statusFilter = (tableFilters?.po_status as string[]) || []
  setFilters(prev => ({ ...prev, po_status: statusFilter }))
  const sortField = sorter.field as string | undefined
  const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
  setSortBy(sortField || '')
  setSortOrder(sortDir)
}}
```

### 9.3 列宽与截断规范

- 需要截断的列：设 `maxWidth` + `ellipsis: true` + `onCell` 注入 CSS 截断样式
- `scroll.x='max-content'` 会阻止原生 ellipsis 生效，必须通过 `onCell` 补救：

```tsx
{
  title: '列名', dataIndex: 'xxx', maxWidth: 100, ellipsis: true,
  onCell: () => ({ style: { maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
}
```

- 固定列：`fixed: 'left'` 或 `fixed: 'right'`
- `tableLayout="fixed"` 配合截断
