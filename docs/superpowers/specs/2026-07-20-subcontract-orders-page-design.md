# Design: 物料齐套中心 — 委外订单 (`subcontract_order`)

**Date:** 2026-07-20
**Status:** Approved, pending implementation
**Scope:** 在「物料齐套中心」下新增「委外订单」页面：头表 + 行内展开明细；完整 CRUD（手动新增 + ERP 同步共存）；独立权限键 `materials.subcontract_orders`。

---

## 1. Background

- 业务侧需要查看/管理委外加工单据：每张单是一个头 + N 行物料明细，并关联销售订单。
- 现状：
  - 后端模型已建好：`backend/app/models/material/subcontract_order.py`（头）、`subcontract_order_detail.py`（明细）。两张表已通过 Alembic 迁移 `add_subcontract_order_tables` 落库。
  - ERP 同步 service 已实现：`erp_sync_service.sync_subcontract_orders` / `sync_subcontract_order_details`，并在 `sync_sql_config` 种子里放了占位 SQL（待业务方填真实 ERP SQL）。
  - 手动触发同步的接口 `POST /api/v1/basicdata/sync/subcontract_orders` 已通。
  - **缺口**：没有读/列表/CRUD API、没有 Pydantic schema、没有前端页面和菜单项、没有权限注册。

---

## 2. 用户确认的设计决策

| 决策点 | 选择 |
|---|---|
| 页面定位 | **完整 CRUD**（手动 + ERP 共存） |
| 列表形态 | **头表 + 行内展开明细**（Table expandable） |
| 筛选条件 | 仅 `bill_no` 模糊匹配（v1） |
| 权限键 | 新建 `materials.subcontract_orders`（独立粒度） |
| 字段策略 | **不新增列**，沿用现有模型字段；后续如需 owner/内部状态再走 `init_database.py` 的 `migrate_columns` |

---

## 3. 数据模型（已存在，不改动）

### 3.1 `subcontract_order`（头）
关键字段：`bill_no`（唯一）、`bill_date`、`bill_type`、`supplier_id`、`status`、`voided_flag`、`closed_flag`、`data_source`、`erp_updated_at`。详见 `backend/app/models/material/subcontract_order.py`。

### 3.2 `subcontract_order_detail`（明细）
关键字段：`erp_order_id`（外键到头的 `erp_order_id`）、`detail_id`、`material_id`、`qty`、`delivery_qty`、`received_qty`、`amount`、`sale_order_id`、`sale_order_no`、`data_source`。唯一约束 `(erp_order_id, detail_id)`。

### 3.3 头/明细关联
两表通过 `erp_order_id` 关联（非主键 `id`）。**注意**：手动新增的头会先 insert 拿到 `id`，但 `erp_order_id` 可空。为支持手动场景：
- 手动新增头时，**用头的 `id` 回填 `erp_order_id`**（让两表始终能 JOIN）。否则纯 ERP 字段会断链。
- ERP 同步时按原逻辑用 ERP 提供的 `erp_order_id`。

> 该回填逻辑放在 create endpoint 内，对 ERP 同步路径无影响。

---

## 4. 后端改动

### 4.1 新增 Schemas（`backend/app/schemas/material/schemas.py`）

```python
class SubcontractOrderDetailOut(BaseModel):
    id: int
    erp_order_id: int | None
    detail_id: int | None
    line_no: int | None
    material_id: int | None
    qty: Decimal | None
    delivery_qty: Decimal | None
    received_qty: Decimal | None
    returned_qty: Decimal | None
    amount: Decimal | None
    sale_order_id: int | None
    sale_order_no: str | None
    mrp_closed_flag: int | None
    data_source: str | None
    model_config = ConfigDict(from_attributes=True)

class SubcontractOrderOut(BaseModel):
    id: int
    erp_order_id: int | None
    bill_no: str
    bill_date: date | None
    bill_type: str | None
    settlement_method: str | None
    settle_date: date | None
    supplier_id: int | None
    department_id: int | None
    salesman_id: int | None
    manager_id: int | None
    auditor_id: int | None
    audit_date: date | None
    creator_id: int | None
    remark: str | None
    voided_flag: int | None
    closed_flag: int | None
    status: str | None
    close_date: date | None
    data_source: str | None
    created_at: datetime
    updated_at: datetime
    detail_count: int = 0           # 派生
    total_qty: Decimal | None = None  # 派生：sum(qty)
    model_config = ConfigDict(from_attributes=True)

class SubcontractOrderDetailCreate(BaseModel):
    material_id: int | None = None
    qty: Decimal | None = None
    delivery_qty: Decimal | None = None
    sale_order_no: str | None = None
    sale_order_id: int | None = None
    remark: str | None = None

class SubcontractOrderCreate(BaseModel):
    bill_no: str
    bill_date: date | None = None
    bill_type: str | None = None
    supplier_id: int | None = None
    status: str | None = None
    remark: str | None = None
    details: list[SubcontractOrderDetailCreate] = []

class SubcontractOrderUpdate(BaseModel):
    bill_date: date | None = None
    bill_type: str | None = None
    supplier_id: int | None = None
    status: str | None = None
    remark: str | None = None

class SubcontractOrderBatchUpdate(BaseModel):
    ids: list[int]
    status: str | None = None
    remark: str | None = None
```

### 4.2 新增 API（`backend/app/api/v1/material/subcontract_orders.py`）

所有 endpoint 权限 = `materials.subcontract_orders.<action>`。

| Method | Path | 说明 |
|---|---|---|
| GET | `/subcontract-orders` | 分页列表（头）。Query: `page, page_size, keyword`(模糊 bill_no)。返回 `PageResult[SubcontractOrderOut]`，每行附 `detail_count` 和 `total_qty`（用子查询聚合）。**默认排除 `voided_flag=1`**，提供 `include_voided=true` 覆盖 |
| GET | `/subcontract-orders/{id}` | 头详情 + 明细数组 |
| GET | `/subcontract-orders/{id}/details` | 单独拉明细（前端展开行调用），分页 |
| POST | `/subcontract-orders` | 新建头（+ 可选嵌套明细）。手动新建时 `data_source='manual'`，并把 `erp_order_id` 设为新生成的 `id` 保证 JOIN |
| PUT | `/subcontract-orders/{id}` | 更新头。**禁止更新 `data_source='erp'` 的行的 ERP 字段**（仅允许更新 remark/status 等无关 ERP 同步的字段） |
| DELETE | `/subcontract-orders/{id}` | 删头（级联删明细）。**禁止删 `data_source='erp'` 的行**（避免被同步重新创建导致脏数据），返回 409 |
| POST | `/subcontract-orders/batch-update` | 批量改 status / remark |
| POST | `/subcontract-orders/import` | CSV 导入（参考 `import_material_csv.import_purchase_plan_csv`） |
| GET | `/subcontract-orders/export` | 导出 CSV/xlsx（参考现有 `purchase_plan.export`） |
| POST | `/subcontract-orders/{id}/details` | 给头追加一行明细 |
| PUT | `/subcontract-orders/{id}/details/{detail_id}` | 更新明细 |
| DELETE | `/subcontract-orders/{id}/details/{detail_id}` | 删明细 |

**Audit log**：所有写操作调用 `log_audit(db, "subcontract_order", ...)`，参考 `purchase_orders.py:115`。

### 4.3 Service：CSV 导入（`backend/app/services/material/import_material_csv.py`）

新增 `import_subcontract_order_csv(path, db)`，参考 `import_purchase_plan_csv`。
- CSV 表头对齐：`bill_no, bill_date, bill_type, supplier_id, status, remark, material_id, qty, sale_order_no`
- 按 `bill_no` 幂等：存在且 `data_source in ('erp', None, '')` → 跳过（不覆盖 ERP）；存在且 `data_source='manual'` → 更新；不存在 → 插入
- 新插入的 `data_source='excel'`（与 purchase_plan 保持一致）

### 4.4 Router 挂载

- `backend/app/api/v1/material/__init__.py` 加 `from .subcontract_orders import router as subcontract_orders_router`，并导出。
- `backend/app/api/v1/__init__.py` 加 `api_router.include_router(material.subcontract_orders_router, prefix="/subcontract-orders", tags=["物料齐套中心-委外订单"])`

### 4.5 权限注册（`backend/app/core/permission_registry.py`）

```python
declare_permission(
    "materials.subcontract_orders", "委外订单",
    module="materials", parent_code="materials",
    route_path="/subcontract-orders", sort_order=8,
)
```

`sort_order=8` 紧跟 `materials.stock_check`(=7) 之后。

### 4.6 角色权限种子（`backend/init_database.py` 的 role seed）

| 角色 | 权限 |
|---|---|
| `admin` | `["create","read","update","delete","import"]` |
| `purchase_manager` | `["create","read","update","delete","import"]` |
| `purchaser` | `["create","read","update","import"]` |
| `planner` | `["read"]` |
| `manager` | `["read"]` |
| `warehouse_keeper` | `["read"]` |
| `quality` | `["read"]` |

权限会在 `lifespan` 启动时由 `sync_permissions_to_db()` 自动 sync 到 DB。

### 4.7 路径 → 权限映射（`backend/app/core/security.py`）

`_SHARE_PATH_TO_RESOURCE` 字典加 `"/subcontract-orders": "materials.subcontract_orders"`（用作 DB 不可用时的 fallback，参考 L97-108 现有条目）。

### 4.8 ERP 同步 guard 验证

现有 `erp_sync_service.sync_subcontract_orders` 已经做了 `data_source in ('erp', None, '')` 检查（与其它表一致），符合 AGENTS.md 要求。**不改动**。

---

## 5. 前端改动

### 5.1 菜单（`frontend/src/layouts/MainLayout.tsx` L186-194）

在物料齐套中心 children 末尾加：
```tsx
{ key: '/subcontract-orders', icon: <ProfileOutlined />, label: '委外订单', permission: 'materials.subcontract_orders' },
```

### 5.2 路由（`frontend/src/App.tsx`）

加 `<Route path="/subcontract-orders" element={<SubcontractOrders />} />`，参考 PurchasePlan 路由。

### 5.3 权限映射（`frontend/src/store/permission.ts`）

`ROUTE_PERMISSION_MAP` 加 `'/subcontract-orders': 'materials.subcontract_orders'`。

### 5.4 API 服务（`frontend/src/services/api.ts`）

在 物料齐套中心 区段（L139 之后）加 `subcontractOrderApi`：
```ts
export const subcontractOrderApi = {
  list: (params) => api.get('/subcontract-orders', { params }),
  get: (id) => api.get(`/subcontract-orders/${id}`),
  details: (id, params) => api.get(`/subcontract-orders/${id}/details`, { params }),
  create: (data) => api.post('/subcontract-orders', data),
  update: (id, data) => api.put(`/subcontract-orders/${id}`, data),
  remove: (id) => api.delete(`/subcontract-orders/${id}`),
  batchUpdate: (data) => api.post('/subcontract-orders/batch-update', data),
  importCsv: (file) => { /* FormData POST */ },
  export: (params) => api.get('/subcontract-orders/export', { params, responseType: 'blob' }),
  addDetail: (id, data) => api.post(`/subcontract-orders/${id}/details`, data),
  updateDetail: (id, detailId, data) => api.put(`/subcontract-orders/${id}/details/${detailId}`, data),
  removeDetail: (id, detailId) => api.delete(`/subcontract-orders/${id}/details/${detailId}`),
};
```

### 5.5 页面（`frontend/src/pages/MaterialCenter/SubcontractOrders/index.tsx`）

**布局**：参考 `pages/MaterialCenter/PurchasePlan/index.tsx`。

- 顶部：统计卡片（总单数、未关闭、已作废）+ 工具栏（搜索 bill_no、新增、导入、导出、批量操作）
- 主表：Ant Design Table，列：`bill_no / bill_date / bill_type / supplier_id / status / detail_count / total_qty / data_source / 操作`
- **展开行**：`expandable.expandedRowRender` 渲染嵌套 Table 显示该单的明细列表（按需懒加载，点击展开时才请求 `/details`）。明细列：`line_no / material_id / qty / delivery_qty / received_qty / sale_order_no / 操作`
- 编辑：抽屉/弹窗表单（头字段）+ 行内编辑或弹窗（明细）
- ERP 行的视觉标识：`data_source === 'erp'` 的行加 tag "ERP 同步"，编辑按钮置灰 + tooltip "ERP 数据请在 ERP 系统修改"
- 导入：复用 PurchasePlan 的 CSV 上传 modal 模式

---

## 6. 不在本次范围

- ERP 真实 SQL 配置（业务方后续在「同步SQL配置」页面填写）
- 与销售订单详情页的交叉跳转（v2）
- owner / 内部状态 等扩展字段（按需走 `migrate_columns`）
- 明细的物料名称解析（JOIN 物料主数据）— v1 显示 `material_id`，后续如需可加 JOIN

---

## 7. 验证清单

| 项 | 方法 |
|---|---|
| 表已存在 | `python init_database.py` 跑完后 `\d subcontract_order` 在 psql 可见 |
| API 列表 | `GET /api/v1/material/subcontract-orders?page=1` 返回 `{code:0, data:{items:[], total:0}}` |
| 手动新增 | POST 创建后 GET 能看到，`data_source='manual'`，`erp_order_id == id` |
| ERP guard | 把一行手动 update `data_source='erp'` 后，再调 PUT 改 ERP 字段应 400 |
| 删除 guard | DELETE 一条 `data_source='erp'` 的行应 409 |
| 权限 | 用 purchaser01 登录能新增；用 planner01 登录只能看不能增 |
| 前端类型 | `npm run build` 通过（唯一 typecheck） |
| 菜单显示 | purchaser01 登录后侧边栏「物料齐套中心」下出现「委外订单」 |

---

## 8. 关键文件清单

**新增**
- `backend/app/api/v1/material/subcontract_orders.py`
- `frontend/src/pages/MaterialCenter/SubcontractOrders/index.tsx`

**修改**
- `backend/app/schemas/material/schemas.py`
- `backend/app/services/material/import_material_csv.py`
- `backend/app/api/v1/material/__init__.py`
- `backend/app/api/v1/__init__.py`
- `backend/app/core/permission_registry.py`
- `backend/app/core/security.py`
- `backend/init_database.py`（角色权限种子）
- `frontend/src/layouts/MainLayout.tsx`
- `frontend/src/App.tsx`
- `frontend/src/store/permission.ts`
- `frontend/src/services/api.ts`
