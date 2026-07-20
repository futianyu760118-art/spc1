# 6 张表格增强搜索 / 筛选 / 排序 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为物料盘点 - 最近盘点单、客户、供应商、物料、人员、库存这 6 张表统一添加顶部 keyword 搜索 + 列排序 + 列筛选(下拉多选),其中物料页移除树形视图,后端扩展 1 个盘点单端点。

**Architecture:** 新建 1 个 `useAntTableQuery` hook(`frontend/src/hooks/useAntTableQuery.ts`)统一管理 keyword(防抖 300ms) / pagination / sortInfo / filters 状态,产出 AntD `<Table>` 所需的 `pagination` + `onChange` + `dataSource` + `loading`,6 个页面复用。后端扩展 `materials/stock-check/recent` 端点(加 `keyword`/`status`/`date_from`/`date_to`/`sort_by`/`sort_order`),5 个基础数据端点**不动**(已支持)。物料页删除 `viewMode` 树形 toggle、tree 视图与 `fetchTreeData`/`buildTreeData` 等辅助函数,但保留 `parentTreeData` 供 MaterialForm 的 TreeSelect 使用。

**Tech Stack:** React 18 + TypeScript + AntD 5(`Table` `onChange` 钩子 + `Input.Search` + `DatePicker`)、FastAPI + SQLAlchemy async(沿用 `_apply_sort` 模式)。

## Global Constraints

- `npm run build` (i.e. `tsc -b && vite build`) 是**唯一**前端 typecheck,每次任务完成都要跑。
- 前端 axios 拦截器 (`frontend/src/services/api.ts`) 把 `response.data.code !== 0` 视为失败,所有接口读取用 `res.data.items / total / page / page_size`。
- 成功响应必须 `ResponseModel(data={...})` 信封,后端不准裸返回。
- `get_db()` 在 `app/core/database.py` 自动 commit/rollback,后端逻辑内**不**手动 commit/rollback。
- 加注释仅在用户明确要求时;默认不写注释。
- 后端 5 个基础数据端点**禁止改动**;只扩展 `materials/stock-check/recent`。
- 物料页:删除树形视图 toggle、tree 视图、`fetchTreeData` / `buildTreeData` / `flattenTree` 调用,但**保留** `parentTreeData` 给 `MaterialForm` 的 `TreeSelect` 用。
- `frontend/src/constants/employeeStatus.ts` 已有 `EMPLOYEE_STATUS_FILTERS` 常量,人员页直接复用。

---

## Task 1: 创建共享 hook `useAntTableQuery`

**Files:**
- Create: `frontend/src/hooks/useAntTableQuery.tsx` (使用 `.tsx` 扩展名,因代码含 JSX;`import '@/hooks/useAntTableQuery'` 不带扩展名,仍可解析)

**Step 1: 创建文件并写入完整 hook 实现**

创建 `D:\wanghuazheng\project\SPC-v2\frontend\src\hooks\useAntTableQuery.ts`,内容如下:

```ts
import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Input } from 'antd'
import type { InputRef } from 'antd'

export interface AntTableFetchParams {
  page: number
  page_size: number
  keyword?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  [k: string]: unknown
}

export interface AntTableFetchResult<T = unknown> {
  items: T[]
  total: number
}

export interface UseAntTableQueryOptions<TFilters extends Record<string, unknown> = Record<string, unknown>> {
  fetchData: (params: AntTableFetchParams & TFilters) => Promise<AntTableFetchResult>
  defaultPageSize?: number
  filterToQuery?: (filters: Record<string, (string | number)[] | null>) => TFilters
  debounceMs?: number
  initialKeyword?: string
}

export interface UseAntTableQueryResult {
  data: any[]
  loading: boolean
  total: number
  keyword: string
  searchInput: React.ReactNode
  tableProps: {
    dataSource: any[]
    loading: boolean
    pagination: {
      current: number
      pageSize: number
      total: number
      showSizeChanger: boolean
      showTotal: (total: number) => string
      pageSizeOptions: string[]
      onChange: (page: number, pageSize: number) => void
    }
    onChange: (
      pagination: { current?: number; pageSize?: number },
      filters: Record<string, (string | number)[] | null>,
      sorter: { field?: string | number; order?: 'ascend' | 'descend' | null },
    ) => void
  }
  reload: () => void
}

export function useAntTableQuery<TFilters extends Record<string, unknown> = Record<string, unknown>>(
  options: UseAntTableQueryOptions<TFilters>,
): UseAntTableQueryResult {
  const { fetchData, defaultPageSize = 20, filterToQuery, debounceMs = 300, initialKeyword = '' } = options

  const [keyword, setKeyword] = useState<string>(initialKeyword)
  const [debouncedKeyword, setDebouncedKeyword] = useState<string>(initialKeyword)
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(defaultPageSize)
  const [sortBy, setSortBy] = useState<string | undefined>(undefined)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc' | undefined>(undefined)
  const [filters, setFilters] = useState<Record<string, (string | number)[] | null>>({})
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState<number>(0)
  const [loading, setLoading] = useState<boolean>(false)
  const [reloadTick, setReloadTick] = useState<number>(0)

  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<InputRef>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedKeyword(keyword), debounceMs)
    return () => clearTimeout(t)
  }, [keyword, debounceMs])

  useEffect(() => {
    setPage(1)
  }, [debouncedKeyword, sortBy, sortOrder, JSON.stringify(filters)])

  useEffect(() => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLoading(true)
    const extra = filterToQuery ? filterToQuery(filters) : ({} as TFilters)
    const params: AntTableFetchParams & TFilters = {
      page,
      page_size: pageSize,
      keyword: debouncedKeyword || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      ...extra,
    }
    fetchData(params)
      .then((res) => {
        if (ctrl.signal.aborted) return
        setData(res.items || [])
        setTotal(res.total || 0)
      })
      .catch((err) => {
        if (ctrl.signal.aborted) return
        console.error('[useAntTableQuery] fetch failed:', err)
        setData([])
        setTotal(0)
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
  }, [page, pageSize, debouncedKeyword, sortBy, sortOrder, JSON.stringify(filters), reloadTick])

  const onChange = useCallback(
    (
      pagination: { current?: number; pageSize?: number },
      nextFilters: Record<string, (string | number)[] | null>,
      sorter: { field?: string | number; order?: 'ascend' | 'descend' | null },
    ) => {
      if (pagination.current) setPage(pagination.current)
      if (pagination.pageSize && pagination.pageSize !== pageSize) {
        setPageSize(pagination.pageSize)
        setPage(1)
      }
      setFilters(nextFilters || {})
      const fieldKey = typeof sorter.field === 'string' ? sorter.field : undefined
      if (fieldKey && (sorter.order === 'ascend' || sorter.order === 'descend')) {
        setSortBy(fieldKey)
        setSortOrder(sorter.order === 'ascend' ? 'asc' : 'desc')
      } else {
        setSortBy(undefined)
        setSortOrder(undefined)
      }
    },
    [pageSize],
  )

  const reload = useCallback(() => setReloadTick((n) => n + 1), [])

  const searchInput = useMemo(
    () => (
      <Input.Search
        ref={inputRef}
        placeholder="搜索"
        allowClear
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        style={{ width: 240 }}
      />
    ),
    [keyword],
  )

  const tableProps: UseAntTableQueryResult['tableProps'] = {
    dataSource: data,
    loading,
    pagination: {
      current: page,
      pageSize,
      total,
      showSizeChanger: true,
      showTotal: (t: number) => `共 ${t} 条`,
      pageSizeOptions: ['20', '50', '100'],
      onChange: (p: number, ps: number) => onChange({ current: p, pageSize: ps }, filters, { order: sortOrder === 'asc' ? 'ascend' : sortOrder === 'desc' ? 'descend' : null, field: sortBy }),
    },
    onChange,
  }

  return { data, loading, total, keyword, searchInput, tableProps, reload }
}
```

**Step 2: 验证 typecheck 通过**

```bash
cd frontend
npm run build
```

预期:`tsc -b` 通过、`vite build` 完成(没有错误)。如果只有其他模块的错误不是本任务引起的,继续。

---

## Task 2: 后端扩展 `materials/stock-check/recent` 端点

**Files:**
- Modify: `backend/app/api/v1/material/stock_check.py` (lines 58-72)
- Modify: `backend/app/services/material/stock_check_service.py` (lines 257-266, `list_recent_stock_checks`)

**Step 1: 修改 service 函数,接收额外参数**

编辑 `D:\wanghuazheng\project\SPC-v2\backend\app\services\material\stock_check_service.py`:

把现有的 `list_recent_stock_checks` (line 257-266) 替换为:

```python
async def list_recent_stock_checks(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 10,
    *,
    keyword: Optional[str] = None,
    status: Optional[List[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> List[StockCheck]:
    SORTABLE = {
        'check_no': StockCheck.check_no,
        'order_no': StockCheck.order_no,
        'check_date': StockCheck.check_date,
        'total_materials': StockCheck.total_materials,
        'checked_materials': StockCheck.checked_materials,
        'total_diff_qty': StockCheck.total_diff_qty,
        'created_at': StockCheck.created_at,
    }
    query = select(StockCheck)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(
            StockCheck.check_no.ilike(like),
            StockCheck.order_no.ilike(like),
            StockCheck.title.ilike(like),
        ))
    if status:
        statuses = [s.strip() for s in status if s and s.strip()]
        if statuses:
            query = query.where(StockCheck.status.in_(statuses))
    if date_from:
        query = query.where(StockCheck.check_date >= date_from)
    if date_to:
        query = query.where(StockCheck.check_date <= date_to)
    if sort_by and sort_by in SORTABLE:
        col = SORTABLE[sort_by]
        if sort_order == 'asc':
            query = query.order_by(col.asc().nullslast())
        else:
            query = query.order_by(col.desc().nullslast())
    else:
        query = query.order_by(StockCheck.created_at.desc())
    rows = (await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(rows)
```

在文件顶部 import 区(大约 line 10)新增 `from sqlalchemy import or_`(与现有 `select, func, desc` 同行)。

**Step 2: 修改 API 端点,接受新 query 参数并把它们转给 service**

编辑 `D:\wanghuazheng\project\SPC-v2\backend\app\api\v1\material\stock_check.py`,把 `recent` 函数(line 58-72)替换为:

```python
@router.get("/stock-check/recent", response_model=ResponseModel[PageResult[StockCheckListOut]])
async def recent(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索盘点单号/订单号/标题"),
    status: Optional[str] = Query(None, description="状态筛选,逗号分隔(open/in_progress/completed/cancelled)"),
    date_from: Optional[date] = Query(None, description="盘点日期起点 (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="盘点日期终点 (YYYY-MM-DD)"),
    sort_by: Optional[str] = Query(None, description="排序字段:check_no/order_no/check_date/total_materials/checked_materials/total_diff_qty/created_at"),
    sort_order: Optional[str] = Query(None, description="asc/desc,默认 desc"),
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    statuses = [s.strip() for s in (status or "").split(",") if s.strip()] or None
    rows = await list_recent_stock_checks(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=statuses,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    filter_query = select(StockCheck)
    if keyword:
        like = f"%{keyword}%"
        filter_query = filter_query.where(or_(
            StockCheck.check_no.ilike(like),
            StockCheck.order_no.ilike(like),
            StockCheck.title.ilike(like),
        ))
    if statuses:
        filter_query = filter_query.where(StockCheck.status.in_(statuses))
    if date_from:
        filter_query = filter_query.where(StockCheck.check_date >= date_from)
    if date_to:
        filter_query = filter_query.where(StockCheck.check_date <= date_to)
    total = (await db.execute(
        select(func.count()).select_from(filter_query.subquery())
    )).scalar() or 0
    return ResponseModel(data=PageResult(
        total=int(total),
        page=page,
        page_size=page_size,
        items=[StockCheckListOut.model_validate(r) for r in rows],
    ))
```

在文件顶部 import 区(大约 line 1-30)新增 `from datetime import date` 和 `from sqlalchemy import or_`。

**Step 3: 验证后端无语法错误**

```bash
cd backend
python -c "import app.api.v1.material.stock_check; import app.services.material.stock_check_service; print('OK')"
```

预期:输出 `OK`。如果有 import 错误,检查 import 行。

---

## Task 3: StockCheck 最近盘点单接入 hook

**Files:**
- Modify: `frontend/src/pages/OrderDelivery/StockCheck/index.tsx` (lines 70-79 fetch 函数, 360-398 表格块)

**Step 1: 修改 `loadRecent` 函数签名,接受 params 对象**

编辑 `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\OrderDelivery\StockCheck\index.tsx`:

把 `loadRecent` (line 70-79) 替换为:

```tsx
  const loadRecent = useCallback(async (params: {
    page?: number
    page_size?: number
    keyword?: string
    sort_by?: string
    sort_order?: 'asc' | 'desc'
    status?: string[]
    date_from?: string
    date_to?: string
  } = {}) => {
    try {
      const { page: p = 1, page_size: ps = 20, ...rest } = params
      const query: any = { page: p, page_size: ps }
      if (rest.keyword) query.keyword = rest.keyword
      if (rest.status?.length) query.status = rest.status.join(',')
      if (rest.date_from) query.date_from = rest.date_from
      if (rest.date_to) query.date_to = rest.date_to
      if (rest.sort_by) query.sort_by = rest.sort_by
      if (rest.sort_order) query.sort_order = rest.sort_order
      const res: any = await materialApi.getRecentStockChecks(query)
      setRecent(res.data?.items || [])
      setRecentTotal(res.data?.total || 0)
      setRecentPage(p)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载最近盘点失败')
    }
  }, [])
```

更新下方所有 `loadRecent(...)` 调用:
- line 103 `await loadRecent(1)` → `await loadRecent({ page: 1 })`
- line 137 `loadRecent(recentPage)` → 改为不直接调用,改用 hook 驱动(下一步)

**Step 2: 替换 useEffect + 表格块,接入 hook**

在文件顶部 import 加入:

```tsx
import { useAntTableQuery } from '@/hooks/useAntTableQuery'
import { DatePicker } from 'antd'
```

替换 `loadRecent` 之后的 useEffect (line 135-139) 为:

```tsx
  useEffect(() => {
    if (!activeCheck) {
      // hook drives reload; nothing to do here
    }
  }, [activeCheck])
```

(此 useEffect 留作占位,保留原结构;实际刷新由 hook 处理。)

在 `loadRecent` 函数之后、原有 useEffect 之前,新增 hook 调用:

```tsx
  const STATUS_OPTIONS = [
    { text: '待盘点', value: 'open' },
    { text: '进行中', value: 'in_progress' },
    { text: '已完成', value: 'completed' },
    { text: '已取消', value: 'cancelled' },
  ]

  const {
    tableProps: recentTableProps,
    searchInput: recentSearchInput,
    keyword: recentKeyword,
  } = useAntTableQuery({
    fetchData: async (params) => {
      const res: any = await materialApi.getRecentStockChecks({
        page: params.page,
        page_size: params.page_size,
        keyword: params.keyword,
        sort_by: params.sort_by,
        sort_order: params.sort_order,
        status: (params.status as string[] | undefined)?.join(','),
        date_from: params.date_from,
        date_to: params.date_to,
      })
      return { items: res.data?.items || [], total: res.data?.total || 0 }
    },
    filterToQuery: (filters) => ({
      status: filters.status as string[] | undefined,
    }),
  })

  const [dateRange, setDateRange] = useState<[string?, string?]>([])

  const reloadRecent = useCallback(() => {
    setRecentPage(1)
    loadRecent({ page: 1, keyword: recentKeyword })
  }, [recentKeyword, loadRecent])
```

将原本"最近盘点单"块(line 361-399)替换为:

```tsx
      ) : (
        <div className="card-modern" style={{ padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <h3 style={{ margin: 0 }}>最近盘点单</h3>
            <Space wrap>
              {recentSearchInput}
              <DatePicker.RangePicker
                onChange={(d) => {
                  setDateRange([
                    d?.[0]?.format('YYYY-MM-DD'),
                    d?.[1]?.format('YYYY-MM-DD'),
                  ])
                }}
              />
              <Button icon={<ReloadOutlined />} onClick={reloadRecent}>刷新</Button>
            </Space>
          </div>
          <Table
            rowKey="id"
            dataSource={recentTableProps.dataSource}
            loading={recentTableProps.loading}
            pagination={recentTableProps.pagination}
            onChange={recentTableProps.onChange}
            scroll={{ x: 1400 }}
            columns={[
              { title: '盘点单号', dataIndex: 'check_no', width: 180, sorter: true },
              { title: '订单号', dataIndex: 'order_no', width: 180, sorter: true },
              { title: '标题', dataIndex: 'title', ellipsis: true },
              {
                title: '状态', dataIndex: 'status', width: 100,
                filters: STATUS_OPTIONS,
                render: (v: any) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.label || v}</Tag>,
              },
              { title: '盘点日期', dataIndex: 'check_date', width: 120, sorter: true },
              { title: '应盘', dataIndex: 'total_materials', width: 70, align: 'right' as const, sorter: true },
              { title: '已盘', dataIndex: 'checked_materials', width: 70, align: 'right' as const, sorter: true },
              {
                title: '总差异', dataIndex: 'total_diff_qty', width: 100, align: 'right' as const, sorter: true,
                render: (v: any) => v != null ? Number(v).toFixed(2) : '-',
              },
              { title: '创建人', dataIndex: 'created_by', width: 100 },
              { title: '创建时间', dataIndex: 'created_at', width: 160, sorter: true, render: (v: any) => v ? formatDateTime(v) : '-' },
              {
                title: '操作', key: 'op', width: 100, fixed: 'right' as const,
                render: (_: any, r: StockCheck) => (
                  <Button type="link" size="small" onClick={() => loadCheck(r.id)}>详情</Button>
                ),
              },
            ]}
          />
        </div>
      )}
```

**Step 3: 验证 typecheck**

```bash
cd frontend
npm run build
```

预期:零 TypeScript 错误。如果有 "cannot find module '@/hooks/useAntTableQuery'",检查 `vite.config.ts` 和 `tsconfig.json` 的 `paths` 里有 `"@/*": ["src/*"]`(已存在,Task 1 文件路径正确即可)。

---

## Task 4: 客户页 (Customers) 接入 hook

**Files:**
- Modify: `frontend/src/pages/BasicDataCenter/Customers.tsx` (lines 1-180)

**Step 1: 重写整个文件**

替换 `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\BasicDataCenter\Customers.tsx` 完整内容为:

```tsx
import { useState, useCallback } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, message,
  Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import { useAntTableQuery } from '../../hooks/useAntTableQuery'

interface Customer {
  id: number
  customer_code: string
  customer_name: string
  customer_short?: string
  customer_level?: string
  industry_type?: string
  credit_code?: string
  status: number
  create_time: string
  update_time?: string
}

const STATUS_FILTERS = [
  { text: '启用', value: '1' },
  { text: '禁用', value: '0' },
]

const LEVEL_FILTERS = [
  { text: 'A类', value: 'A' },
  { text: 'B类', value: 'B' },
  { text: 'C类', value: 'C' },
]

const CustomerForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="customer_code" label="客户编码" rules={[{ required: true }]}>
      <Input placeholder="请输入客户编码" />
    </Form.Item>
    <Form.Item name="customer_name" label="客户名称" rules={[{ required: true }]}>
      <Input placeholder="请输入客户名称" />
    </Form.Item>
    <Form.Item name="customer_short" label="客户简称">
      <Input placeholder="请输入客户简称" />
    </Form.Item>
    <Form.Item name="customer_level" label="客户等级">
      <Select placeholder="请选择客户等级">
        <Select.Option value="A">A类</Select.Option>
        <Select.Option value="B">B类</Select.Option>
        <Select.Option value="C">C类</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="industry_type" label="所属行业">
      <Input placeholder="请输入所属行业" />
    </Form.Item>
    <Form.Item name="credit_code" label="统一社会信用代码">
      <Input placeholder="请输入统一社会信用代码" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Customers() {
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Customer | null>(null)
  const [form] = Form.useForm()
  const [reloadTick, setReloadTick] = useState(0)

  const fetchCustomers = useCallback(async (params: any) => {
    const res: any = await api.get('/basicdata/customers', { params })
    return { items: res.data?.items || [], total: res.data?.total || 0 }
  }, [])

  const { tableProps, searchInput, reload } = useAntTableQuery({
    fetchData: fetchCustomers,
    filterToQuery: (filters) => ({
      customer_level: (filters.customer_level as string[] | undefined)?.join(','),
      status: (filters.status as string[] | undefined)?.join(','),
    }),
  })

  const refresh = useCallback(() => {
    setReloadTick((n) => n + 1)
    reload()
  }, [reload])

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: Customer) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/customers/${id}`)
      message.success('删除成功')
      refresh()
    } catch {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        await api.put(`/basicdata/customers/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/customers', values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      refresh()
    } catch {
      message.error('操作失败')
    }
  }

  const columns = [
    { title: '客户编码', dataIndex: 'customer_code', key: 'customer_code', sorter: true },
    { title: '客户名称', dataIndex: 'customer_name', key: 'customer_name', sorter: true },
    { title: '客户简称', dataIndex: 'customer_short', key: 'customer_short', sorter: true },
    {
      title: '客户等级', dataIndex: 'customer_level', key: 'customer_level',
      filters: LEVEL_FILTERS,
      render: (v?: string) => v || '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      filters: STATUS_FILTERS,
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: any, record: Customer) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>{searchInput}</Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={columns}
          {...tableProps}
          scroll={{ x: 800 }}
          size="small"
        />
      </div>
      <Modal
        title={editingItem ? '编辑客户' : '新增客户'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <CustomerForm form={form} />
      </Modal>
    </div>
  )
}
```

**Step 2: 验证 typecheck**

```bash
cd frontend
npm run build
```

预期:零错误。注意 `reloadTick` 暂未挂接到任何 useEffect(若需要可加,当前实现下 hook 内 effect 已覆盖刷新),保留 state 不影响。

---

## Task 5: 供应商页 (Suppliers) 接入 hook

**Files:**
- Modify: `frontend/src/pages/BasicDataCenter/Suppliers.tsx`

**Step 1: 重写整个文件**

替换 `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\BasicDataCenter\Suppliers.tsx` 完整内容为:

```tsx
import { useState, useCallback } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import { useAntTableQuery } from '../../hooks/useAntTableQuery'

interface Supplier {
  id: number
  supplier_code: string
  supplier_name: string
  supplier_short?: string
  supplier_type?: string
  contact_person?: string
  contact_phone?: string
  fax?: string
  address?: string
  erp_supply_id?: number
  payment_terms?: string
  status: number
  create_time: string
  update_time?: string
}

const STATUS_FILTERS = [
  { text: '启用', value: '1' },
  { text: '禁用', value: '0' },
]

const TYPE_FILTERS = [
  { text: '生产', value: '生产' },
  { text: '贸易', value: '贸易' },
  { text: '服务', value: '服务' },
]

const SupplierForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="supplier_code" label="供应商编码" rules={[{ required: true }]}>
      <Input placeholder="请输入供应商编码" />
    </Form.Item>
    <Form.Item name="supplier_name" label="供应商名称" rules={[{ required: true }]}>
      <Input placeholder="请输入供应商名称" />
    </Form.Item>
    <Form.Item name="supplier_short" label="供应商简称">
      <Input placeholder="请输入供应商简称" />
    </Form.Item>
    <Form.Item name="supplier_type" label="供应商类型">
      <Input placeholder="请输入供应商类型" />
    </Form.Item>
    <Form.Item name="contact_person" label="联系人">
      <Input placeholder="请输入联系人" />
    </Form.Item>
    <Form.Item name="contact_phone" label="联系电话">
      <Input placeholder="请输入联系电话" />
    </Form.Item>
    <Form.Item name="fax" label="传真">
      <Input placeholder="请输入传真" />
    </Form.Item>
    <Form.Item name="address" label="地址">
      <Input placeholder="请输入地址" />
    </Form.Item>
    <Form.Item name="erp_supply_id" label="ERP供应商ID">
      <InputNumber style={{ width: '100%' }} placeholder="请输入ERP内部ID" />
    </Form.Item>
    <Form.Item name="payment_terms" label="付款条款">
      <Input placeholder="请输入付款条款" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Suppliers() {
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Supplier | null>(null)
  const [form] = Form.useForm()

  const { tableProps, searchInput, reload } = useAntTableQuery({
    fetchData: async (params: any) => {
      const res: any = await api.get('/basicdata/suppliers', { params })
      return { items: res.data?.items || [], total: res.data?.total || 0 }
    },
    filterToQuery: (filters) => ({
      supplier_type: (filters.supplier_type as string[] | undefined)?.join(','),
      status: (filters.status as string[] | undefined)?.join(','),
    }),
  })

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: Supplier) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/suppliers/${id}`)
      message.success('删除成功')
      reload()
    } catch {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        await api.put(`/basicdata/suppliers/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/suppliers', values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      reload()
    } catch {
      message.error('操作失败')
    }
  }

  const columns = [
    { title: '供应商编码', dataIndex: 'supplier_code', key: 'supplier_code', width: 140, sorter: true },
    { title: '供应商名称', dataIndex: 'supplier_name', key: 'supplier_name', width: 200, ellipsis: true, sorter: true },
    { title: '简称', dataIndex: 'supplier_short', key: 'supplier_short', width: 120, ellipsis: true, sorter: true },
    {
      title: '类型', dataIndex: 'supplier_type', key: 'supplier_type', width: 100,
      filters: TYPE_FILTERS,
      render: (v?: string) => v || '-',
    },
    { title: '联系人', dataIndex: 'contact_person', key: 'contact_person', width: 100, sorter: true },
    { title: '电话', dataIndex: 'contact_phone', key: 'contact_phone', width: 130 },
    { title: '传真', dataIndex: 'fax', key: 'fax', width: 130 },
    { title: '地址', dataIndex: 'address', key: 'address', width: 200, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      filters: STATUS_FILTERS,
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作', key: 'action', width: 100, fixed: 'right' as const,
      render: (_: any, record: Supplier) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>{searchInput}</Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={columns}
          {...tableProps}
          scroll={{ x: 1200 }}
          size="small"
        />
      </div>
      <Modal
        title={editingItem ? '编辑供应商' : '新增供应商'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={640}
      >
        <SupplierForm form={form} />
      </Modal>
    </div>
  )
}
```

**Step 2: 验证 typecheck**

```bash
cd frontend
npm run build
```

预期:零错误。

---

## Task 6: 物料页 (Materials) 接入 hook 并删除树形视图

**Files:**
- Modify: `frontend/src/pages/BasicDataCenter/Materials.tsx`

**Step 1: 重写整个文件**

替换 `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\BasicDataCenter\Materials.tsx` 完整内容为:

```tsx
import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Space, Tag, Popconfirm, Row, Col, TreeSelect,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import { useAntTableQuery } from '../../hooks/useAntTableQuery'

interface Material {
  id: number
  erp_material_id: number
  parent_id?: number | null
  material_code: string
  material_name: string
  spec_model?: string
  material_type: string
  unit_of_measure: string
  brand?: string
  is_purchase: number
  is_produce: number
  status: number
  erp_sync_flag: number
  is_deleted: number
}

interface TreeNode {
  id: number
  value: number
  title: string
  key: number
  children?: TreeNode[]
}

const buildTreeData = (items: Material[]): TreeNode[] => {
  const map: Record<number, TreeNode> = {}
  const roots: TreeNode[] = []
  for (const item of items) {
    map[item.erp_material_id] = { id: item.erp_material_id, value: item.erp_material_id, title: `${item.material_code} - ${item.material_name}`, key: item.erp_material_id, children: [] }
  }
  for (const item of items) {
    if (item.parent_id && map[item.parent_id]) {
      map[item.parent_id].children!.push(map[item.erp_material_id])
    } else {
      roots.push(map[item.erp_material_id])
    }
  }
  return roots
}

const filterSelfFromTree = (nodes: TreeNode[], excludeId: number): TreeNode[] => {
  return nodes
    .filter(n => n.id !== excludeId)
    .map(n => ({
      ...n,
      children: n.children ? filterSelfFromTree(n.children, excludeId) : [],
    }))
}

const STATUS_FILTERS = [
  { text: '启用', value: '1' },
  { text: '禁用', value: '0' },
]

const MaterialForm = ({ form, treeData }: { form: any, treeData: TreeNode[] }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="erp_material_id" label="ERP物料ID" rules={[{ required: true }]}>
      <InputNumber placeholder="请输入ERP物料ID" style={{ width: '100%' }} />
    </Form.Item>
    <Form.Item name="parent_id" label="上级物料">
      <TreeSelect
        treeData={treeData}
        placeholder="无（根级物料）"
        allowClear
        treeDefaultExpandAll
      />
    </Form.Item>
    <Form.Item name="material_code" label="物料编码" rules={[{ required: true }]}>
      <Input placeholder="请输入物料编码" />
    </Form.Item>
    <Form.Item name="material_name" label="物料名称" rules={[{ required: true }]}>
      <Input placeholder="请输入物料名称" />
    </Form.Item>
    <Form.Item name="spec_model" label="规格型号">
      <Input placeholder="请输入规格型号" />
    </Form.Item>
    <Form.Item name="material_type" label="物料分类" rules={[{ required: true }]}>
      <Input placeholder="请输入物料分类" />
    </Form.Item>
    <Form.Item name="unit_of_measure" label="计量单位" rules={[{ required: true }]}>
      <Input placeholder="请输入计量单位" />
    </Form.Item>
    <Form.Item name="brand" label="品牌/厂商">
      <Input placeholder="请输入品牌/厂商" />
    </Form.Item>
    <Form.Item name="is_purchase" label="是否可采购" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="is_produce" label="是否可生产" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="erp_sync_flag" label="ERP同步标识" initialValue={0}>
      <Select>
        <Select.Option value={1}>已同步</Select.Option>
        <Select.Option value={0}>未同步</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Materials() {
  const [parentTreeData, setParentTreeData] = useState<TreeNode[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Material | null>(null)
  const [form] = Form.useForm()

  const { tableProps, searchInput, reload } = useAntTableQuery({
    fetchData: async (params: any) => {
      const res: any = await api.get('/basicdata/materials', { params })
      return { items: res.data?.items || [], total: res.data?.total || 0 }
    },
    filterToQuery: (filters) => ({
      material_type: (filters.material_type as string[] | undefined)?.join(','),
      status: (filters.status as string[] | undefined)?.join(','),
    }),
  })

  const fetchParentTree = useCallback(async () => {
    try {
      const res: any = await api.get('/basicdata/materials', { params: { page: 1, page_size: 1000 } })
      setParentTreeData(buildTreeData(res.data?.items || []))
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchParentTree()
  }, [fetchParentTree])

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: Material) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (materialId: number) => {
    try {
      await api.delete(`/basicdata/materials/${materialId}`)
      message.success('删除成功')
      reload()
      fetchParentTree()
    } catch {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        if (values.parent_id === editingItem.erp_material_id) {
          message.error('上级物料不能选择自身')
          return
        }
        await api.put(`/basicdata/materials/${editingItem.erp_material_id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/materials', values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      reload()
      fetchParentTree()
    } catch {
      message.error('操作失败')
    }
  }

  const columns = [
    { title: 'ERP物料ID', dataIndex: 'erp_material_id', key: 'erp_material_id', width: 120, sorter: true },
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 160, sorter: true },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180, sorter: true },
    { title: '规格型号', dataIndex: 'spec_model', key: 'spec_model', width: 140, sorter: true, ellipsis: true },
    {
      title: '物料分类', dataIndex: 'material_type', key: 'material_type', width: 100,
      filters: [
        { text: '原材料', value: '原材料' },
        { text: '半成品', value: '半成品' },
        { text: '成品', value: '成品' },
        { text: '包装', value: '包装' },
      ],
    },
    { title: '计量单位', dataIndex: 'unit_of_measure', key: 'unit_of_measure', width: 80, sorter: true },
    { title: '品牌/厂商', dataIndex: 'brand', key: 'brand', width: 100 },
    {
      title: '可采购', dataIndex: 'is_purchase', key: 'is_purchase', width: 70,
      render: (v: number) => <Tag color={v ? 'blue' : 'default'}>{v ? '是' : '否'}</Tag>,
    },
    {
      title: '可生产', dataIndex: 'is_produce', key: 'is_produce', width: 70,
      render: (v: number) => <Tag color={v ? 'blue' : 'default'}>{v ? '是' : '否'}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 70,
      filters: STATUS_FILTERS,
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作', key: 'action', width: 100, fixed: 'right' as const,
      render: (_: any, record: Material) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.erp_material_id)} okText="确认" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>{searchInput}</Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={columns}
          {...tableProps}
          scroll={{ x: 1100 }}
          size="small"
        />
      </div>
      <Modal
        title={editingItem ? '编辑物料' : '新增物料'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <MaterialForm form={form} treeData={editingItem ? filterSelfFromTree(parentTreeData, editingItem.erp_material_id) : parentTreeData} />
      </Modal>
    </div>
  )
}
```

**Step 2: 验证 typecheck**

```bash
cd frontend
npm run build
```

预期:零错误。

---

## Task 7: 人员页 (Employees) 接入 hook

**Files:**
- Modify: `frontend/src/pages/BasicDataCenter/Employees.tsx`

**Step 1: 重写整个文件**

替换 `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\BasicDataCenter\Employees.tsx` 完整内容为:

```tsx
import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import { useAntTableQuery } from '../../hooks/useAntTableQuery'
import { EMPLOYEE_STATUS_OPTIONS, EMPLOYEE_STATUS_FILTERS, getEmployeeStatusMeta } from '../../constants/employeeStatus'

interface Employee {
  id: number
  emp_code: string
  emp_name: string
  org_id: number
  position_id?: number
  position?: string
  position_name?: string
  oa_user_id?: string
  manager_oa_user_id?: string
  manager_name?: string
  phone?: string
  email?: string
  status: number
  create_time: string
}

interface Position {
  id: number
  position_code: string
  position_name: string
  status: number
}

const EmployeeForm = ({ form, positions, employees }: { form: any, positions: Position[], employees: Employee[] }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="emp_code" label="员工工号" rules={[{ required: true }]}>
      <Input placeholder="请输入员工工号" />
    </Form.Item>
    <Form.Item name="emp_name" label="员工姓名" rules={[{ required: true }]}>
      <Input placeholder="请输入员工姓名" />
    </Form.Item>
    <Form.Item name="org_id" label="所属组织ID" rules={[{ required: true }]}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入所属组织ID" />
    </Form.Item>
    <Form.Item name="position_id" label="岗位">
      <Select
        allowClear
        showSearch
        placeholder="请选择岗位"
        optionFilterProp="label"
        options={positions.map(position => ({
          value: position.id,
          label: `${position.position_name} (${position.position_code})`,
        }))}
      />
    </Form.Item>
    <Form.Item name="manager_oa_user_id" label="上级人员">
      <Select
        allowClear
        showSearch
        placeholder="请选择上级人员"
        optionFilterProp="label"
        options={employees
          .filter(emp => emp.emp_code)
          .map(emp => ({
            value: emp.oa_user_id || emp.emp_code,
            label: `${emp.emp_name} (${emp.emp_code})`,
          }))}
      />
    </Form.Item>
    <Form.Item name="phone" label="手机号">
      <Input placeholder="请输入手机号" />
    </Form.Item>
    <Form.Item name="email" label="邮箱">
      <Input placeholder="请输入邮箱" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        {EMPLOYEE_STATUS_OPTIONS.map(option => (
          <Select.Option key={option.value} value={option.value}>{option.label}</Select.Option>
        ))}
      </Select>
    </Form.Item>
  </Form>
)

export default function Employees() {
  const [positions, setPositions] = useState<Position[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Employee | null>(null)
  const [form] = Form.useForm()

  const { data, tableProps, searchInput, reload } = useAntTableQuery({
    fetchData: async (params: any) => {
      const res: any = await api.get('/basicdata/employees', { params })
      return { items: res.data?.items || [], total: res.data?.total || 0 }
    },
    filterToQuery: (filters) => ({
      status: (filters.status as string[] | undefined)?.join(','),
    }),
  })

  useEffect(() => {
    const fetchPositions = async () => {
      try {
        const res: any = await api.get('/basicdata/positions', { params: { page: 1, page_size: 100, status: '1' } })
        setPositions(res.data?.items || [])
      } catch {
        message.error('加载岗位列表失败')
      }
    }
    fetchPositions()
  }, [])

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: Employee) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/employees/${id}`)
      message.success('删除成功')
      reload()
    } catch {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        await api.put(`/basicdata/employees/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/employees', values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      reload()
    } catch {
      message.error('操作失败')
    }
  }

  const columns = [
    { title: '员工工号', dataIndex: 'emp_code', key: 'emp_code', sorter: true },
    { title: '员工姓名', dataIndex: 'emp_name', key: 'emp_name', sorter: true },
    { title: '所属组织ID', dataIndex: 'org_id', key: 'org_id', sorter: true },
    {
      title: '岗位', dataIndex: 'position_name', key: 'position_name', sorter: true,
      render: (_: any, record: Employee) => record.position_name || record.position || '-',
    },
    {
      title: '上级', dataIndex: 'manager_name', key: 'manager_name',
      render: (text: string) => text || '-',
    },
    { title: '手机号', dataIndex: 'phone', key: 'phone', sorter: true },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      filters: EMPLOYEE_STATUS_FILTERS,
      filterMultiple: true,
      render: (status: number) => {
        const meta = getEmployeeStatusMeta(status)
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: any, record: Employee) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>{searchInput}</Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={columns}
          {...tableProps}
          scroll={{ x: 1000 }}
          size="small"
        />
      </div>
      <Modal
        title={editingItem ? '编辑人员' : '新增人员'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <EmployeeForm form={form} positions={positions} employees={data} />
      </Modal>
    </div>
  )
}
```

**Step 2: 验证 typecheck**

```bash
cd frontend
npm run build
```

预期:零错误。

---

## Task 8: 库存页 (Inventory) 接入 hook

**Files:**
- Modify: `frontend/src/pages/BasicDataCenter/Inventory.tsx`

**Step 1: 重写整个文件**

替换 `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\BasicDataCenter\Inventory.tsx` 完整内容为:

```tsx
import { useState, useCallback, useEffect } from 'react'
import { Table, Button, Input, message, Space, Row, Col, Statistic, Select } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import api from '../../services/api'
import { useAntTableQuery } from '../../hooks/useAntTableQuery'

interface InventoryItem {
  id: number
  material_id: number
  material_code: string
  material_name: string
  wh_id: number
  wh_code: string
  wh_name: string
  location_id: number | null
  location_name: string
  qty_on_hand: number
  locked_qty: number
  balance_qty: number
  qty_in_transit: number
  batch_no: string
  created_at: string
  updated_at: string
}

interface Warehouse {
  id: number
  wh_code: string
  wh_name: string
}

export default function Inventory() {
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])

  useEffect(() => {
    api.get('/basicdata/warehouses', { params: { page: 1, page_size: 200 } })
      .then((res: any) => setWarehouses(res.data?.items || []))
      .catch(() => { /* ignore */ })
  }, [])

  const { data, tableProps, searchInput, reload } = useAntTableQuery({
    fetchData: async (params: any) => {
      const res: any = await api.get('/basicdata/inventory', { params })
      return { items: res.data?.items || [], total: res.data?.total || 0 }
    },
    filterToQuery: (filters) => ({
      wh_code: (filters.wh_code as string[] | undefined)?.[0],
      batch_no: (filters.batch_no as string[] | undefined)?.[0],
    }),
  })

  const totals = data.reduce(
    (acc: any, item: InventoryItem) => ({
      onHand: acc.onHand + (item.qty_on_hand || 0),
      locked: acc.locked + (item.locked_qty || 0),
      balance: acc.balance + (item.balance_qty || 0),
      inTransit: acc.inTransit + (item.qty_in_transit || 0),
    }),
    { onHand: 0, locked: 0, balance: 0, inTransit: 0 },
  )

  const warehouseFilters = warehouses.map(w => ({ text: `${w.wh_code} ${w.wh_name}`, value: w.wh_code }))

  const columns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 120, sorter: true },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 160, ellipsis: true, sorter: true },
    {
      title: '仓库编码', dataIndex: 'wh_code', key: 'wh_code', width: 100,
      sorter: true,
      filters: warehouseFilters,
    },
    { title: '仓库名称', dataIndex: 'wh_name', key: 'wh_name', width: 120 },
    { title: '库位名称', dataIndex: 'location_name', key: 'location_name', width: 120, ellipsis: true },
    {
      title: '库存量', dataIndex: 'qty_on_hand', key: 'qty_on_hand', width: 100, align: 'right' as const,
      sorter: true, render: (v: number) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '锁定数量', dataIndex: 'locked_qty', key: 'locked_qty', width: 100, align: 'right' as const,
      sorter: true, render: (v: number) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '结存数量', dataIndex: 'balance_qty', key: 'balance_qty', width: 100, align: 'right' as const,
      sorter: true, render: (v: number) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '在途库存', dataIndex: 'qty_in_transit', key: 'qty_in_transit', width: 100, align: 'right' as const,
      render: (v: number) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '批次号', dataIndex: 'batch_no', key: 'batch_no', width: 100,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <Input
            placeholder="精确批次号"
            value={selectedKeys[0] || ''}
            onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
            onPressEnter={confirm}
            style={{ width: 188, marginBottom: 8, display: 'block' }}
          />
          <Space>
            <Button type="primary" size="small" onClick={confirm}>确定</Button>
            <Button size="small" onClick={clearFilters}>重置</Button>
          </Space>
        </div>
      ),
      onFilterDropdownOpenChange: (open: boolean) => { if (!open) { /* keep */ } },
    },
    {
      title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 160,
      sorter: true, render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN') : '-'),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col>{searchInput}</Col>
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button>
            </Space>
          </Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col><Statistic title="库存量合计" value={totals.onHand} precision={2} /></Col>
          <Col><Statistic title="锁定数量合计" value={totals.locked} precision={2} /></Col>
          <Col><Statistic title="结存数量合计" value={totals.balance} precision={2} /></Col>
          <Col><Statistic title="在途库存合计" value={totals.inTransit} precision={2} /></Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={columns}
          {...tableProps}
          scroll={{ x: 1400 }}
          size="small"
        />
      </div>
    </div>
  )
}
```

**Step 2: 验证 typecheck**

```bash
cd frontend
npm run build
```

预期:零错误。如果报 `Input`/`Select` 未使用 import,从 import 移除(本任务用到了 Input/Input 在 filterDropdown 内,Select 可移除)。

---

## Task 9: 最终验证

**Step 1: 运行完整 typecheck**

```bash
cd frontend
npm run build
```

预期:零 TypeScript 错误。`vite build` 输出 `dist/` 目录。

**Step 2: 确认 import 清理**

如果 Task 8 报 `Select` 未使用,移除 `Select` from import;如果其他任务有 unused import,清理掉。

**Step 3: 提交所有改动**

```bash
git add -A
git status
```

预期:列出 7 个修改文件 + 1 个新文件 (`frontend/src/hooks/useAntTableQuery.ts`)。**不**自动 commit,由用户决定。
