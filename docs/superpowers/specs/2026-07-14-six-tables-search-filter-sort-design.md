# Design: 6 张表格增强搜索 / 筛选 / 排序

**Date:** 2026-07-14
**Status:** Approved, pending implementation
**Scope:** Frontend 重构 6 张 AntD Table + 后端扩展 1 个端点 (`materials/stock-check/recent`)。

---

## 1. Background

仓库内 6 张核心列表都使用裸 AntD `<Table>`,搜索/筛选/排序能力缺失或极弱:

| 页面 | 现状 |
|---|---|
| 物料盘点 - 最近盘点单 | 纯展示,无搜索无排序无筛选 |
| 基础数据 - 客户 | 纯展示,无搜索无排序无筛选 |
| 基础数据 - 供应商 | 纯展示,无搜索无排序无筛选 |
| 基础数据 - 物料 | 树形/列表双视图,均无搜索无排序无筛选 |
| 基础数据 - 人员 | 纯展示,无搜索无排序无筛选 |
| 基础数据 - 库存 | 仅有 keyword 框,无排序无筛选 |

后端 5 个基础数据端点的 `keyword` / `sort_by` / `sort_order` / 类型 / 状态筛选**均已就绪**。`materials/stock-check/recent` 是唯一后端缺位的端点。

仓库已有 1 个 ProTable 范例 (`Purchase/PriceChange/list.tsx`) 和 1 个未挂载的旧实现 (`BasicDataManagement.tsx`),均可作为模式参考。

---

## 2. 已复用的基础设施

| 已存在 | 用途 |
|---|---|
| 后端 `keyword` ILIKE + `sort_by/sort_order` + CSV 枚举筛选模式 (`basicdata.py` 5 个端点) | 5 张基础数据表直接复用,零后端改动 |
| `frontend/src/services/api.ts` 单例 axios + `useAuthStore` | 接口统一调用,无需新建 |
| AntD `Table` `onChange(pagination, filters, sorter)` | 一处状态钩子即可驱动整张表 |
| AntD `Input.Search` | 顶部搜索框,沿用各页原有按钮风格 |
| 物料页 tree/list 双视图 (`Materials.tsx`) | **本次删除 tree 视图**,只保留 list |

**结论:共享 1 个 hook 即可统一 6 张表的状态管理;后端只需补 1 个端点。**

---

## 3. 共享 Hook 设计

**新文件:** `frontend/src/hooks/useAntTableQuery.ts`

```ts
interface UseAntTableQueryOptions<TFilters extends Record<string, unknown>> {
  fetchData: (params: {
    page: number
    page_size: number
    keyword?: string
    sort_by?: string
    sort_order?: 'asc' | 'desc'
  } & TFilters) => Promise<{ items: any[]; total: number }>
  defaultPageSize?: number
  filterToQuery?: (filters: Record<string, (string | number)[] | null>) => TFilters
  debounceMs?: number
}

interface UseAntTableQueryResult {
  searchInput: React.ReactNode        // 自动 300ms 防抖的 Input.Search
  tableParams: {
    dataSource: any[]
    loading: boolean
    pagination: { current, pageSize, total, showSizeChanger }
    onChange: (pagination, filters, sorter) => void
  }
  reload: () => void
  keyword: string
}
```

**职责:**
- 持有 `keyword`(防抖 300ms)、`pagination`、`sortInfo`、`filters` 状态
- `useEffect` 监听上述状态变化 → 调用 `fetchData` → 写回 `dataSource`/`total`
- `onChange` 钩子统一处理 pagination / filters / sorter 的状态写入
- `searchInput` 渲染 `<Input.Search>` 并自动绑定防抖
- 卸载时取消未完成的请求(`AbortController`)

**列配置约定:**
- 文本/数字列: `sorter: true`
- 枚举列(状态/类型/等级/仓库): `filters: [{text, value}]`,多选用 `filterMultiple: true`
- 日期列(盘点日期): `sorter: true`;日期范围筛选在工具栏用 2 个 `<DatePicker>` 绑定到 `date_from` / `date_to`

---

## 4. 页面改造矩阵

| 页面 | 顶部工具栏 | 列筛选维度 | 排序列 | 后端 |
|---|---|---|---|---|
| 最近盘点单 | 搜索 + 刷新 | 状态 / 盘点日期范围 | 单号/订单号/日期/应盘/已盘/差异/创建时间 | **需扩展** |
| 客户 | 搜索 + 刷新 + 新增 | 等级 / 状态 | 编码/名称/简称/等级 | 不变 |
| 供应商 | 搜索 + 刷新 + 新增 | 类型 / 状态 | 编码/名称/类型 | 不变 |
| 物料 | 搜索 + 刷新 + 新增 | 类型 / 状态 | 编码/名称/规格/类型/单位 | 不变 |
| 人员 | 搜索 + 刷新 + 新增 | 状态 | 工号/姓名/组织/岗位/手机号 | 不变 |
| 库存 | 搜索(已存在) + 刷新 | 仓库编码 / 批次号 | 编码/仓库编码/库存量/锁定/结存/更新时间 | 不变 |

---

## 5. 最近盘点单后端扩展

**文件:** `backend/app/api/v1/material/stock_check.py` 的 `/materials/stock-check/recent` 端点 + `backend/app/services/material/stock_check_service.py` 的 `list_recent_stock_checks()`

### 5.1 新增 Query 参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `keyword` | str, optional | `check_no` / `order_no` / `title` 任一 ILIKE |
| `status` | str, optional | CSV, 枚举 `open/in_progress/completed/cancelled` |
| `date_from` | date, optional | `check_date >= date_from` |
| `date_to` | date, optional | `check_date <= date_to` |
| `sort_by` | str, optional | 白名单: `check_no, order_no, check_date, total_materials, checked_materials, total_diff_qty, created_at` |
| `sort_order` | str, optional | `asc` / `desc`,默认 `desc` |

### 5.2 默认行为
- 无任何过滤参数时:**保持当前行为**(全表按 `created_at DESC` 分页),**保兼容**
- `sort_by` 不在白名单 → 静默 fallback 到 `created_at`
- 状态/日期范围无值 → 不加 WHERE

### 5.3 实现模式
与 `basicdata.py:78-217` (customers/suppliers) 完全一致:
- `SORTABLE` 字典做白名单
- `WHERE` 子句按可选参数拼接
- 复用现有的 `ResponseModel(data={items, total, page, page_size})` 信封

---

## 6. 物料页改造 (删除树形视图)

**文件:** `frontend/src/pages/BasicDataCenter/Materials.tsx`

### 删除
- `viewMode` state (`'tree'` | `'list'`)
- 顶部 `树形 / 列表` 按钮 (lines 282-294)
- `getTree()` 服务调用 + `treeData` state
- `getMaterialTree()` 调用
- `defaultExpandAllRows` / `pagination={false}` 的 tree 分支
- `MaterialTreeNode` 相关 import (如有)

### 保留
- 列表视图的 10 个列定义
- 顶部 `[刷新] [新增]` 按钮
- 编辑/删除 modal/抽屉

### 新增
- 顶部 `Input.Search` 绑定到 `useAntTableQuery` 的 `searchInput`
- 列配置加 `sorter: true` / `filters: [...]`
- 移入新 hook

### 风险
- 现有用户习惯:tree 默认全展开,实际就是平铺列表,功能等价,影响极小
- 文件预计从 347 行 → ~270 行

---

## 7. 文件清单

### 新建 (1 个)
- `frontend/src/hooks/useAntTableQuery.ts`

### 修改 (7 个)
- `frontend/src/pages/OrderDelivery/StockCheck/index.tsx`
- `frontend/src/pages/BasicDataCenter/Customers.tsx`
- `frontend/src/pages/BasicDataCenter/Suppliers.tsx`
- `frontend/src/pages/BasicDataCenter/Materials.tsx` (同时删除树形)
- `frontend/src/pages/BasicDataCenter/Employees.tsx`
- `frontend/src/pages/BasicDataCenter/Inventory.tsx`
- `backend/app/api/v1/material/stock_check.py`
- `backend/app/services/material/stock_check_service.py`

### 不动
- `frontend/src/pages/BasicDataCenter/BasicDataManagement.tsx` (旧实现,未挂载,保留作历史参考)
- `frontend/src/pages/Purchase/PriceChange/list.tsx` (ProTable 范例,仅作参考,不动)

---

## 8. 验证清单

### 通用 (6 张表)
1. 顶部 `Input.Search` 输入 → 300ms 后表格刷新
2. 列 header 点击 sort 按钮 → 表格按该列升降序切换
3. 列 header filter 下拉(状态/类型等)勾选 → 表格筛选
4. 多选 filter 取消勾选 → 表格回到全量
5. 搜索 + 筛选 + 排序 同时生效,互不冲突
6. 刷新数据(翻页) → 搜索词/筛选/排序不丢失
7. 切页/改 pageSize → 状态保留
8. `npm run build` 通过

### 最近盘点单 (额外)
9. 不带任何参数 → 行为与改动前一致(全表按 `created_at DESC`)
10. `?keyword=PO-001` → 命中 `check_no`/`order_no`/`title` 任一
11. `?status=open,in_progress` → CSV 多值筛选生效
12. `?date_from=2026-07-01&date_to=2026-07-14` → `check_date` 区间生效
13. `?sort_by=total_diff_qty&sort_order=desc` → 差异倒序
14. `?sort_by=evil_column` → 静默 fallback 到 `created_at`,不报错

### 物料页 (额外)
15. 进入 `/basicdata/materials` → 不再显示 `树形/列表` 切换按钮
16. 列表默认按 `material_code` 升序(沿用后端默认)
17. 旧 tree 数据不再被请求 (`/basicdata/materials/tree` 调用次数 = 0)

---

## 9. 风险/范围外

- 不做搜索高亮(用户输入匹配的文字不高亮)
- 不做"最近搜索词"记忆(只用本地 state)
- 不做列可见性配置(其他任务已用 `ui_preferences.visibleColumns`,本次不交叉)
- 不做导出 CSV/Excel(超出范围)
- 不做 Inventory 的统计卡片改版(只动表格部分)
- 不改后端已存在端点的字段(只扩展 `recent`)
- 不动 `init_database.py` / Alembic(无 schema 变更)
