# Design: 物料盘点 (`scm_inventory_check`)

**Date:** 2026-07-14
**Status:** Approved, pending implementation
**Scope:** New 物料视角盘点单 + 行表 (`scm_inventory_check` + `scm_inventory_check_item`), 新 API / 前端页面, 完全废除现有 `OrderInventoryCheck` (JSONB 快照式) 全部前后端代码.

---

## 1. Background

现有功能 `OrderInventoryCheck` (`scm_order_inventory_check` 表) 是按订单存 JSONB 快照的"齐套概览", 只计算齐套率/到料数等汇总指标, **不记录每行物料的实盘数和盘点标记**. 用户提出的"按物料视角"盘点需求是当前功能的盲区.

用户确认的设计方向:
1. 盘点入口: 订单 → 沿 `SaleOrderLine.bom_id` 展开 BOM
2. 存储: 物料视角 (盘点单头 + 物料行明细)
3. 仅记录实盘数, **不回写 `scm_inventory.qty_on_hand`** (不调账)
4. 废除现有 `OrderInventoryCheck` 全部代码 (保留旧表 + 旧 Alembic 迁移作历史, 防止破坏迁移链)

---

## 2. 新表结构

### 2.1 `scm_inventory_check` (盘点单头)

| 字段 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | BigInteger | PK autoinc | |
| `check_no` | String(32) | UNIQUE NOT NULL | 盘点单号, 格式 `PD{yyyyMMdd}-{seq:03d}` |
| `order_no` | String(64) | NOT NULL, idx | 触发起源订单号 |
| `title` | String(200) | | 标题, 默认 = `订单号 + 日期` |
| `check_type` | String(16) | default `'order'` | `'order'` / `'manual'` / `'cycle_count'` |
| `status` | String(16) | default `'open'` | `'open'` / `'in_progress'` / `'completed'` / `'cancelled'` |
| `check_date` | Date | NOT NULL | 盘点日期 |
| `total_materials` | Integer | default 0 | 应盘物料数 (派生) |
| `checked_materials` | Integer | default 0 | 已盘物料数 (派生) |
| `total_diff_qty` | Numeric(18,4) | default 0 | 总差异数 (派生) |
| `created_by` | String(100) | | |
| `checked_by` | String(100) | nullable | 完工人 |
| `created_at` | DateTime | server_default=now | |
| `updated_at` | DateTime | onupdate=now | |
| `completed_at` | DateTime | nullable | |
| `remark` | Text | | |
| | Index(`order_no`, `check_date`) | | |

### 2.2 `scm_inventory_check_item` (盘点单物料行)

| 字段 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | BigInteger | PK autoinc | |
| `check_id` | BigInteger | NOT NULL, FK→`scm_inventory_check.id`, idx | |
| `line_no` | String(32) | | 关联 SaleOrderLine 行号 (跨行聚合行时为空) |
| `material_id` | BigInteger | idx | |
| `material_code` | String(50) | | 冗余, 便于展示 |
| `material_name` | String(200) | | 冗余 |
| `spec_model` | String(200) | | 冗余 |
| `unit` | String(20) | | 冗余 |
| `req_qty` | Numeric(18,4) | NOT NULL default 0 | 应盘数 (BOM standard_qty × order_qty, 跨行求和) |
| `system_qty` | Numeric(18,4) | default 0 | 库存数 (创建时从 `scm_inventory.qty_on_hand` 聚合快照) |
| `actual_qty` | Numeric(18,4) | nullable | **盘点数** (用户录入) |
| `diff_qty` | Numeric(18,4) | default 0 | 派生: `actual_qty - system_qty` |
| `is_checked` | Integer | default 0 | **盘点标记** (0/1) |
| `checked_at` | DateTime | nullable | 标记时间 |
| `checked_by` | String(100) | nullable | 标记人 |
| `remark` | Text | | |
| `created_at` | DateTime | server_default=now | |
| `updated_at` | DateTime | onupdate=now | |
| | UniqueConstraint(`check_id`, `material_id`, `line_no`) | | |

**派生字段刷新**: 每次 item 写/删, 重新计算头表 `total_materials` / `checked_materials` / `total_diff_qty`.

---

## 3. 删除范围 — 现有 `OrderInventoryCheck`

### 后端 (7 文件 / 7 处)
| 路径 | 操作 |
|---|---|
| `backend/app/models/material/order_inventory_check.py` | 删整文件 |
| `backend/app/models/material/__init__.py` L9 | 删 `OrderInventoryCheck` 导入 |
| `backend/app/api/v1/material/inventory_check.py` | 删整文件 |
| `backend/app/api/v1/material/__init__.py` L10 | 删 `inventory_check_router` 导入 |
| `backend/app/api/v1/__init__.py` L28 | 删 `include_router(... inventory_check_router ...)` |
| `backend/app/core/permission_registry.py` L146 | 删 `declare_permission("orders.inventory_check", ...)` |
| `backend/app/schemas/material/schemas.py` L418-471 | 删 4 个 Pydantic 类 |
| `backend/init_database.py` L537/580/616/657 | 删 4 个角色 permission dict 中 `orders.inventory_check` 项 |
| `backend/app/services/basicdata/position_role_service.py` L52/199/218/289/325/366 | 删 6 个岗位预设中 `orders.inventory_check` 项 |
| `backend/alembic/versions/0100_add_order_inventory_check.py` | **保留** (历史迁移) |
| `backend/alembic/versions/0101_add_inventory_check_permission.py` | **保留** |

### 前端 (4 文件 / 8 处)
| 路径 | 操作 |
|---|---|
| `frontend/src/pages/OrderDelivery/InventoryCheck/index.tsx` + 目录 | 删整文件及目录 |
| `frontend/src/App.tsx` L18 + L179 | 删 import + route |
| `frontend/src/layouts/MainLayout.tsx` L83/179/378/449 | 删 4 处 |
| `frontend/src/services/api.ts` L200-210 | 删 5 个 `materialApi.*InventoryCheck*` 方法 |
| `frontend/src/pages/OrderDelivery/OrderList/index.tsx` L1783-1788 | 把 `navigate('/inventory-check?orderNo=...')` 改为 `/stock-check?orderNo=...` |

---

## 4. 新增 — 后端

### 4.1 模型
- **新文件** `backend/app/models/material/inventory_check.py` — 同时定义 `StockCheck` + `StockCheckItem` 两个类 (`scm_inventory_check` + `scm_inventory_check_item`)
- 修改 `backend/app/models/material/__init__.py` 末尾追加两个新 import

### 4.2 Schemas
- **新文件** `backend/app/schemas/material/stock_check.py`:
  ```python
  class StockCheckCreate(BaseModel):
      order_no: str
      title: Optional[str] = None
      check_date: Optional[date] = None
      remark: Optional[str] = None

  class StockCheckItemUpdate(BaseModel):
      actual_qty: Optional[Decimal] = None
      is_checked: Optional[int] = None
      remark: Optional[str] = None

  class StockCheckItemBatchUpdate(BaseModel):
      items: List[StockCheckItemUpdate]
      check_id: int

  class StockCheckItemOut(BaseModel):
      id, check_id, line_no, material_id, material_code, material_name,
      spec_model, unit, req_qty, system_qty, actual_qty, diff_qty,
      is_checked, checked_at, checked_by, remark
      model_config = {"from_attributes": True}

  class StockCheckOut(BaseModel):
      id, check_no, order_no, title, check_type, status, check_date,
      total_materials, checked_materials, total_diff_qty,
      created_by, checked_by, created_at, updated_at, completed_at, remark
      items: List[StockCheckItemOut] = []
      model_config = {"from_attributes": True}

  class StockCheckListOut(BaseModel):
      id, check_no, order_no, title, status, check_date,
      total_materials, checked_materials, total_diff_qty,
      created_by, checked_by, created_at
      model_config = {"from_attributes": True}
  ```

### 4.3 Service
- **新文件** `backend/app/services/material/stock_check_service.py`
- 关键函数:
  - `create_stock_check_from_order(db, order_no, current_user, **kwargs) -> StockCheck`:
    1. 校验 SaleOrder 存在
    2. 复用 `order_materials_service.get_order_product_materials` 拿 BOM 展开
    3. 跨 line_no 按 `material_id` 聚合, sum `req_qty`
    4. 一次性查 `scm_inventory` 按 `material_id` GROUP BY 拿 `system_qty`
    5. 写头 + 行 (bulk_insert_mappings), 返回 `StockCheckOut`
  - `update_stock_check_item(db, item_id, payload, current_user) -> StockCheckItem`:
    - 写 `actual_qty` / `is_checked` / `remark`, 触发头表 `checked_materials` / `total_diff_qty` 刷新
  - `batch_update_items(db, check_id, items: list[dict], current_user) -> int`
  - `complete_stock_check(db, check_id, current_user) -> StockCheck`: 校验全部 `is_checked==1` 否则 400
  - `cancel_stock_check(db, check_id, current_user) -> StockCheck`
  - `_get_stock_by_material_id(db, material_ids) -> dict[int, Decimal]`: 新 helper, 按 `scm_inventory.material_id` 聚合 `qty_on_hand` (注意现有 helper 是按 `material_code` 聚合 `balance_qty`)

### 4.4 API
- **新文件** `backend/app/api/v1/material/stock_check.py`, 路由前缀 `/materials/stock-check`:

| Method | Path | 用途 | 权限 |
|---|---|---|---|
| POST | `/from-order/{order_no}` | 从订单创建盘点单 | `orders.stock_check` write |
| GET | `/recent` | 全局最近盘点单 (分页) | read |
| GET | `/by-order/{order_no}` | 按订单查盘点单 | read |
| GET | `/{check_id}` | 盘点单详情 (含 items) | read |
| GET | `/{check_id}/items` | 仅物料行 (分页) | read |
| PUT | `/items/{item_id}` | 录入/修改 actual_qty / is_checked (单行) | write |
| POST | `/items/batch` | 批量保存 | write |
| POST | `/{check_id}/complete` | 完结 (校验全部 is_checked=1) | write |
| POST | `/{check_id}/cancel` | 取消盘点单 | write |

### 4.5 路由挂载
- `backend/app/api/v1/material/__init__.py`: 删 L10, 加 `from app.api.v1.material.stock_check import router as stock_check_router`
- `backend/app/api/v1/__init__.py`: 删 L28, 加 `api_router.include_router(material.stock_check_router, prefix="/materials", tags=["物料齐套中心-物料盘点"])`

### 4.6 权限
- `backend/app/core/permission_registry.py`: 删 L146 (`orders.inventory_check`), 加新:
  ```python
  declare_permission(
      "orders.stock_check", "物料盘点",
      module="orders", parent_code="orders",
      route_path="/stock-check", sort_order=5
  )
  ```
- `backend/init_database.py` 4 个角色 (`planner` / `purchaser` / `manager` / `purchase_manager`) 的 `permissions` dict 加 `"orders.stock_check": ["read", "update"]`
- `backend/app/services/basicdata/position_role_service.py` 6 个岗位预设 (`readonly` / `sales` / `purchaser` / `manager` / `director` / `executive`) 加同项

---

## 5. 新增 — 前端

### 5.1 API client
`frontend/src/services/api.ts` `materialApi` 内:
- 删 L200-210 (5 个旧方法)
- 加 9 个新方法:
  ```ts
  createStockCheckFromOrder: (orderNo: string, data?: StockCheckCreate) =>
    api.post(`/materials/stock-check/from-order/${orderNo}`, data),
  getRecentStockChecks: (params) =>
    api.get('/materials/stock-check/recent', { params }),
  getStockChecksByOrder: (orderNo: string) =>
    api.get(`/materials/stock-check/by-order/${orderNo}`),
  getStockCheck: (checkId: number) =>
    api.get(`/materials/stock-check/${checkId}`),
  getStockCheckItems: (checkId: number, params) =>
    api.get(`/materials/stock-check/${checkId}/items`, { params }),
  updateStockCheckItem: (itemId: number, data: StockCheckItemUpdate) =>
    api.put(`/materials/stock-check/items/${itemId}`, data),
  batchUpdateStockCheckItems: (checkId: number, items: StockCheckItemUpdate[]) =>
    api.post('/materials/stock-check/items/batch', { check_id: checkId, items }),
  completeStockCheck: (checkId: number) =>
    api.post(`/materials/stock-check/${checkId}/complete`),
  cancelStockCheck: (checkId: number) =>
    api.post(`/materials/stock-check/${checkId}/cancel`),
  ```

### 5.2 页面
- **新文件** `frontend/src/pages/OrderDelivery/StockCheck/index.tsx` (~500 行)
- 主结构:
  ```
  [搜索: 订单号 ___]  [搜索]  [清空]
  ┌────────────────────────────────┐
  │ 最近盘点单 Table                 │
  │   check_no / order_no / status  │
  │   / 应盘 / 已盘 / 差异           │
  │   / created_by / created_at     │
  │   / [详情] [复制]               │
  └────────────────────────────────┘
  (选中某盘点单后 ↓)
  ← 返回  PD20260714-001  HJ2024-001
  状态: in_progress  应盘 23 / 已盘 18  差异 -5
  [保存全部] [标记完成] [取消盘点]
  ┌────────────────────────────────┐
  │ 物料 Table (可编辑)             │
  │  列: 序号/编码/名称/规格/单位/    │
  │  应盘/库存/盘点数(可编辑)/差异/  │
  │  已盘(可勾)/标记时间/标记人/备注  │
  │  inline edit: actual_qty +      │
  │               is_checked        │
  └────────────────────────────────┘
  ```
- inline edit 用 Ant Design `Table` 的 `components.body.cell` editable 模式, `InputNumber` + `Checkbox`
- 列宽/滚动/卡片样式参考现有 `OrderDelivery/InventoryCheck` 的 `card-modern` 风格
- KPI 卡片用 `Row` + `Col` + `Card size="small"`

### 5.3 路由 + 菜单
- `frontend/src/App.tsx`:
  - 删 L18 `import InventoryCheck from './pages/OrderDelivery/InventoryCheck/index'`
  - 删 L179 `<Route path="inventory-check" element={<InventoryCheck />} />`
  - 加 import + `<Route path="stock-check" element={<StockCheck />} />`
- `frontend/src/layouts/MainLayout.tsx`:
  - 删 L83 `'orders.inventory_check': <CheckOutlined />`
  - 删 L179 菜单项 `{ key: '/inventory-check', icon: <CheckOutlined />, label: '订单物料盘点', permission: 'orders.inventory_check' }`
  - 删 L378 `'/inventory-check': 'order-delivery'`
  - 删 L449 `'/inventory-check': 'orders.inventory_check'`
  - 加 icon `AuditOutlined`, 菜单项 `{ key: '/stock-check', icon: <AuditOutlined />, label: '物料盘点', permission: 'orders.stock_check' }`
  - 加 `'/stock-check': 'order-delivery'` 和 `'/stock-check': 'orders.stock_check'`
- `frontend/src/pages/OrderDelivery/OrderList/index.tsx` L1785: `navigate('/inventory-check?...')` → `navigate('/stock-check?...')`

---

## 6. 数据库 / 迁移

- **不写新 Alembic 迁移**: 新表由 `init_database.py` 的 `Base.metadata.create_all` 容器启动时自动建 (按 AGENTS.md, 这是项目惯例)
- `migrate_columns` 不需要动
- 旧表 `scm_order_inventory_check` **保留**, 数据可作历史审计

---

## 7. 验证清单

1. `cd backend && python -c "from app.models.material.inventory_check import StockCheck, StockCheckItem; print(StockCheck.__tablename__, StockCheckItem.__tablename__)"` — 模型导入正常
2. `cd backend && python init_database.py` — 新表被建, 无报错
3. `cd backend && uvicorn app.main:app --reload` 启动, `GET /api/v1/permissions/tree` 出现 `orders.stock_check` 且不再出现 `orders.inventory_check`
4. admin 登录, 菜单出现"物料盘点", 旧"订单物料盘点"已消失
5. 从 OrderList 点"盘点"按钮 → 跳到 `/stock-check?orderNo=...`
6. 后端自动创建盘点单, 行数与 `get_order_product_materials` 返回的物料行数一致
7. 前端录入 actual_qty, 勾选 is_checked, 保存 → 后端持久化, 头表 `checked_materials` / `total_diff_qty` 自动刷新
8. 点"标记完成" → 状态变 `completed`, `completed_at` / `checked_by` 写入
9. 重新打开盘点单 → 数据持久化
10. `cd frontend && npm run build` — TypeScript 编译通过 (项目唯一的 typecheck)

---

## 8. 风险 / 范围外

- **不调账**: `actual_qty` 不回写 `scm_inventory.qty_on_hand`. 后续如需要, 可加独立"调账"入口
- **单层 BOM 展开**: 与 `get_order_product_materials` 一致, 不递归 phantom assembly. 后续如需, 复用 `kit_analysis_service._get_bom_demand_map` 改写
- **盘点单导出 Excel**: 不做, 后续按需
- **盘点差异审批流**: 不做, 后续按需
- **不删旧表** `scm_order_inventory_check` (避免破坏 Alembic 迁移链)

---

## 9. 文件清单汇总

### 删除 (4 文件 / 1 目录)
1. `backend/app/models/material/order_inventory_check.py`
2. `backend/app/api/v1/material/inventory_check.py`
3. `frontend/src/pages/OrderDelivery/InventoryCheck/index.tsx`
4. `frontend/src/pages/OrderDelivery/InventoryCheck/` (目录)

### 新建 (5 文件)
1. `backend/app/models/material/inventory_check.py`
2. `backend/app/schemas/material/stock_check.py`
3. `backend/app/services/material/stock_check_service.py`
4. `backend/app/api/v1/material/stock_check.py`
5. `frontend/src/pages/OrderDelivery/StockCheck/index.tsx`

### 修改 (10 文件)
1. `backend/app/models/material/__init__.py`
2. `backend/app/api/v1/material/__init__.py`
3. `backend/app/api/v1/__init__.py`
4. `backend/app/core/permission_registry.py`
5. `backend/app/schemas/material/schemas.py`
6. `backend/init_database.py`
7. `backend/app/services/basicdata/position_role_service.py`
8. `frontend/src/App.tsx`
9. `frontend/src/layouts/MainLayout.tsx`
10. `frontend/src/services/api.ts`
11. `frontend/src/pages/OrderDelivery/OrderList/index.tsx`

(End of file)
