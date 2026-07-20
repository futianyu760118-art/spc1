# 待盘点物料池 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a per-user "待盘点物料池" (pending stock-check material pool) inside `MaterialPickerModal` so users can accumulate materials across multiple searches before creating one盘点单.

**Architecture:** Frontend-only. New Zustand store `useStockCheckPoolStore` with manual `localStorage` persistence, namespaced per user (key `spc_stock_check_pool:<userId>`). `MaterialPickerModal` becomes a two-tab UI: `搜索物料` (existing search + new add-to-pool actions) and `待盘点池 (N)` (new pool editor with subset-selectable create). On successful create from the pool, only the *used* materials are auto-removed. The existing `materialApi.createStockCheckFromMaterials` endpoint is reused — no backend changes.

**Tech Stack:** React + TypeScript, Ant Design 5, Zustand (no `persist` middleware — repo uses manual localStorage; pattern from `frontend/src/store/uiPreferences.ts`).

## Global Constraints

- Frontend only — **no backend / DB / schema / migration changes**.
- Follow AGENTS.md: `npm run build` (run from `frontend/`, this is the **only** typecheck) must pass before declaring done. There is no test framework.
- Match existing conventions: TypeScript strict; Ant Design components; Zustand stores under `frontend/src/store/`; camelCase file names.
- Do not bypass the response envelope — backend untouched so unchanged.
- Pool size: at create time, enforce `1 ≤ selected <= 500` (matches backend `stock_check.py:73-74`).
- Per-user scoping: key `spc_stock_check_pool:<userId>`; `auth.ts` calls `loadForUser(user.id)` on `setAuth`, `loadForUser(null)` on `logout`.

---

## Task 1: Create the pool store

**Files:**
- Create: `frontend/src/store/stockCheckPool.ts`

**Step 1.1: Create the file with the full code below.**

`frontend/src/store/stockCheckPool.ts`:

```ts
import { create } from 'zustand'

export interface PoolMaterial {
  erp_material_id: number
  material_code: string | null
  material_name: string | null
  spec_model: string | null
  unit: string | null
  system_qty: number | null
  added_at: string
}

const STORAGE_KEY_PREFIX = 'spc_stock_check_pool'

function storageKeyFor(userId: number | null): string {
  return `${STORAGE_KEY_PREFIX}:${userId ?? 'anon'}`
}

function readPool(userId: number | null): PoolMaterial[] {
  try {
    const raw = localStorage.getItem(storageKeyFor(userId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as PoolMaterial[]) : []
  } catch {
    return []
  }
}

function writePool(userId: number | null, items: PoolMaterial[]): void {
  try {
    localStorage.setItem(storageKeyFor(userId), JSON.stringify(items))
  } catch {
    // localStorage may be unavailable (private mode, quota); silently degrade
  }
}

interface StockCheckPoolState {
  currentUserId: number | null
  items: PoolMaterial[]
  add: (materials: PoolMaterial[]) => void
  remove: (erpMaterialIds: number[]) => void
  clear: () => void
  has: (erpMaterialId: number) => boolean
  loadForUser: (userId: number | null) => void
}

function nowIso(): string {
  return new Date().toISOString()
}

export const useStockCheckPoolStore = create<StockCheckPoolState>((set, get) => {
  return {
    currentUserId: null,
    items: [],

    add: (materials) => {
      const state = get()
      const existing = new Set(state.items.map((m) => m.erp_material_id))
      const incoming = materials.filter((m) => !existing.has(m.erp_material_id))
      if (incoming.length === 0) return
      const stamped = incoming.map((m) => ({ ...m, added_at: m.added_at || nowIso() }))
      const next = [...state.items, ...stamped]
      set({ items: next })
      writePool(state.currentUserId, next)
    },

    remove: (erpMaterialIds) => {
      const state = get()
      const drop = new Set(erpMaterialIds)
      const next = state.items.filter((m) => !drop.has(m.erp_material_id))
      if (next.length === state.items.length) return
      set({ items: next })
      writePool(state.currentUserId, next)
    },

    clear: () => {
      const state = get()
      set({ items: [] })
      writePool(state.currentUserId, [])
    },

    has: (erpMaterialId) => get().items.some((m) => m.erp_material_id === erpMaterialId),

    loadForUser: (userId) => {
      const items = readPool(userId)
      set({ currentUserId: userId, items })
    },
  }
})
```

**Step 1.2: Verify the file compiles.**

Run from `frontend/`:
```bash
npm run build
```
Expected: build succeeds. Fix any TS errors before continuing.

---

## Task 2: Wire `auth.ts` to scope the pool per user

**Files:**
- Edit: `frontend/src/store/auth.ts`

**Step 2.1: Add the import.**

In `frontend/src/store/auth.ts` after the existing import of `useUiPreferencesStore` (line 4), add:

```ts
import { useStockCheckPoolStore } from './stockCheckPool'
```

**Step 2.2: Call `loadForUser` in `setAuth`.**

In the `setAuth` function (around `auth.ts:157-171`), after the existing `useUiPreferencesStore.getState().loadFromUser(user)` line, add:

```ts
      useStockCheckPoolStore.getState().loadForUser(user.id)
```

The resulting block should read:
```ts
    setAuth: (token, user) => {
      localStorage.setItem('token', token)
      if (user) {
        localStorage.setItem('user', JSON.stringify(user))
        useThemeStore.getState().loadFontSizeFromUser(user)
        useUiPreferencesStore.getState().loadFromUser(user)
        useStockCheckPoolStore.getState().loadForUser(user.id)
      }
      const state = get()
      if (!state.shareUser) {
        set({ originalToken: token, originalUser: user, currentToken: token, currentUser: user })
      } else {
        set({ originalToken: token, originalUser: user })
      }
    },
```

**Step 2.3: Call `loadForUser(null)` in `logout`.**

In the `logout` function (around `auth.ts:203-216`), add a call before the final `set({...})`. The full function becomes:

```ts
    logout: () => {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      localStorage.removeItem('shareToken')
      localStorage.removeItem('shareUser')
      useStockCheckPoolStore.getState().loadForUser(null)
      set({
        originalToken: null,
        originalUser: null,
        shareToken: null,
        shareUser: null,
        currentToken: null,
        currentUser: null,
      })
    },
```

**Step 2.4: Verify.**

From `frontend/`:
```bash
npm run build
```
Expected: success.

---

## Task 3: Refactor `MaterialPickerModal.tsx` — wrap in Tabs, add pool tab

**Files:**
- Edit: `frontend/src/pages/MaterialCenter/StockCheck/MaterialPickerModal.tsx`

**Step 3.1: Replace the entire file contents with the new implementation below.**

`frontend/src/pages/MaterialCenter/StockCheck/MaterialPickerModal.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { Modal, Input, Table, Button, Space, message, Pagination, Spin, Tabs, Empty, Popconfirm } from 'antd'
import { SearchOutlined, ClearOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { materialApi } from '@/services/api'
import { useStockCheckPoolStore, PoolMaterial } from '@/store/stockCheckPool'

interface MaterialCandidate {
  erp_material_id: number
  material_code?: string | null
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  system_qty?: number | null
}

interface Props {
  open: boolean
  onCancel: () => void
  onConfirm: (selected: MaterialCandidate[], source: 'search' | 'pool') => void
  confirmLoading?: boolean
}

type TabKey = 'search' | 'pool'

export default function MaterialPickerModal({ open, onCancel, onConfirm, confirmLoading }: Props) {
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [items, setItems] = useState<MaterialCandidate[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [selectedMap, setSelectedMap] = useState<Record<number, MaterialCandidate>>({})

  const [activeTab, setActiveTab] = useState<TabKey>('search')
  const [poolSelectedIds, setPoolSelectedIds] = useState<number[]>([])

  const poolItems = useStockCheckPoolStore((s) => s.items)
  const poolAdd = useStockCheckPoolStore((s) => s.add)
  const poolRemove = useStockCheckPoolStore((s) => s.remove)
  const poolClear = useStockCheckPoolStore((s) => s.clear)
  const poolHas = useStockCheckPoolStore((s) => s.has)

  useEffect(() => {
    if (!open || activeTab !== 'search') return
    let cancelled = false
    setLoading(true)
    materialApi
      .listMaterialCandidates({ keyword: keyword || undefined, page, page_size: pageSize })
      .then((res: any) => {
        if (cancelled) return
        const data = res?.data || {}
        setItems((data.items || []) as MaterialCandidate[])
        setTotal(Number(data.total || 0))
      })
      .catch((err: any) => {
        if (!cancelled) message.error(err?.message || '加载物料候选失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, activeTab, keyword, page, pageSize])

  useEffect(() => {
    if (!open) {
      setSelectedIds(new Set())
      setSelectedMap({})
      setKeyword('')
      setPage(1)
      setActiveTab('search')
      setPoolSelectedIds([])
    }
  }, [open])

  const toggleRow = (row: MaterialCandidate) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(row.erp_material_id)) {
        next.delete(row.erp_material_id)
      } else {
        next.add(row.erp_material_id)
      }
      return next
    })
    setSelectedMap((prev) => {
      const next = { ...prev }
      if (selectedIds.has(row.erp_material_id)) {
        delete next[row.erp_material_id]
      } else {
        next[row.erp_material_id] = row
      }
      return next
    })
  }

  const togglePageAll = () => {
    const allSelected = items.length > 0 && items.every((it) => selectedIds.has(it.erp_material_id))
    setSelectedIds((prev) => {
      const next = new Set(prev)
      setSelectedMap((prevMap) => {
        const nextMap = { ...prevMap }
        items.forEach((it) => {
          if (allSelected) {
            next.delete(it.erp_material_id)
            delete nextMap[it.erp_material_id]
          } else {
            next.add(it.erp_material_id)
            nextMap[it.erp_material_id] = it
          }
        })
        return nextMap
      })
      return next
    })
  }

  const allOnPageSelected = useMemo(
    () => items.length > 0 && items.every((it) => selectedIds.has(it.erp_material_id)),
    [items, selectedIds],
  )

  const handleConfirm = () => {
    if (selectedIds.size === 0) {
      message.warning('请至少选择一个物料')
      return
    }
    onConfirm(Object.values(selectedMap), 'search')
  }

  const handleAddToPool = (rows: MaterialCandidate[]) => {
    if (rows.length === 0) return
    const poolMaterials: PoolMaterial[] = rows.map((r) => ({
      erp_material_id: r.erp_material_id,
      material_code: r.material_code ?? null,
      material_name: r.material_name ?? null,
      spec_model: r.spec_model ?? null,
      unit: r.unit ?? null,
      system_qty: r.system_qty ?? null,
      added_at: new Date().toISOString(),
    }))
    poolAdd(poolMaterials)
    message.success(`已加入待盘点池，当前共 ${poolItems.length} 项`)
  }

  const handleBatchAddToPool = () => {
    if (selectedIds.size === 0) {
      message.warning('请先勾选要加入待盘点池的物料')
      return
    }
    handleAddToPool(Object.values(selectedMap))
    setSelectedIds(new Set())
    setSelectedMap({})
  }

  const handlePoolCreate = () => {
    if (poolSelectedIds.length === 0) {
      message.warning('请至少选择一个物料')
      return
    }
    if (poolSelectedIds.length > 500) {
      message.warning('一次最多创建 500 个物料的盘点单，请减少勾选数量')
      return
    }
    const selected: MaterialCandidate[] = poolSelectedIds.map((id) => {
      const row = poolItems.find((p) => p.erp_material_id === id)
      return {
        erp_material_id: id,
        material_code: row?.material_code ?? null,
        material_name: row?.material_name ?? null,
        spec_model: row?.spec_model ?? null,
        unit: row?.unit ?? null,
        system_qty: row?.system_qty ?? null,
      }
    })
    onConfirm(selected, 'pool')
  }

  const searchColumns = [
    {
      title: (
        <input
          type="checkbox"
          checked={allOnPageSelected}
          onChange={togglePageAll}
          style={{ cursor: 'pointer' }}
        />
      ),
      key: 'select',
      width: 48,
      render: (_: any, row: MaterialCandidate) => (
        <input
          type="checkbox"
          checked={selectedIds.has(row.erp_material_id)}
          onChange={() => toggleRow(row)}
          style={{ cursor: 'pointer' }}
        />
      ),
    },
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 140 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180, ellipsis: true },
    { title: '规格', dataIndex: 'spec_model', key: 'spec_model', width: 160, ellipsis: true },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 70 },
    {
      title: '即时库存',
      dataIndex: 'system_qty',
      key: 'system_qty',
      width: 100,
      align: 'right' as const,
      render: (v: number | null | undefined) => (v == null ? '—' : Number(v).toFixed(2)),
    },
    {
      title: '操作',
      key: 'action',
      width: 130,
      fixed: 'right' as const,
      render: (_: any, row: MaterialCandidate) => {
        const inPool = poolHas(row.erp_material_id)
        return (
          <Button
            size="small"
            type={inPool ? 'default' : 'link'}
            icon={<PlusOutlined />}
            disabled={inPool}
            onClick={() => handleAddToPool([row])}
          >
            {inPool ? '已在池中' : '加入待盘点池'}
          </Button>
        )
      },
    },
  ]

  const poolColumns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 140 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180, ellipsis: true },
    { title: '规格', dataIndex: 'spec_model', key: 'spec_model', width: 160, ellipsis: true },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 70 },
    {
      title: '即时库存(快照)',
      dataIndex: 'system_qty',
      key: 'system_qty',
      width: 130,
      align: 'right' as const,
      render: (v: number | null | undefined) => (v == null ? '—' : Number(v).toFixed(2)),
    },
    {
      title: '加入时间',
      dataIndex: 'added_at',
      key: 'added_at',
      width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '—'),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right' as const,
      render: (_: any, row: PoolMaterial) => (
        <Button
          size="small"
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => {
            poolRemove([row.erp_material_id])
            setPoolSelectedIds((prev) => prev.filter((id) => id !== row.erp_material_id))
          }}
        >
          移除
        </Button>
      ),
    },
  ]

  const searchTab = (
    <>
      <Space style={{ marginBottom: 12 }} size="middle">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索物料编码/名称/规格"
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value)
            setPage(1)
          }}
          style={{ width: 280 }}
        />
        <Button icon={<ClearOutlined />} onClick={() => { setKeyword(''); setPage(1) }}>
          清空
        </Button>
      </Space>
      <Spin spinning={loading}>
        <Table
          rowKey="erp_material_id"
          size="small"
          dataSource={items}
          columns={searchColumns as any}
          pagination={false}
          scroll={{ y: 360 }}
        />
      </Spin>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          pageSizeOptions={['10', '20', '50', '100']}
          onChange={(p, ps) => { setPage(p); setPageSize(ps) }}
          showTotal={(t) => `共 ${t} 项`}
        />
      </div>
    </>
  )

  const poolTab =
    poolItems.length === 0 ? (
      <Empty description="待盘点池为空，请到「搜索物料」标签添加物料" />
    ) : (
      <Table
        rowKey="erp_material_id"
        size="small"
        dataSource={poolItems}
        columns={poolColumns as any}
        pagination={false}
        scroll={{ y: 360 }}
        rowSelection={{
          selectedRowKeys: poolSelectedIds,
          onChange: (keys) => setPoolSelectedIds(keys as number[]),
          preserveSelectedRowKeys: true,
        }}
      />
    )

  const searchFooter = (
    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
      <span>
        已选 <b style={{ color: '#1677ff' }}>{selectedIds.size}</b> 项
      </span>
      <Space>
        <Button onClick={onCancel}>取消</Button>
        <Button onClick={handleBatchAddToPool}>加入待盘点池(已选{selectedIds.size}项)</Button>
        <Button type="primary" loading={confirmLoading} onClick={handleConfirm}>
          确定并创建盘点单
        </Button>
      </Space>
    </Space>
  )

  const poolFooter = (
    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
      <span>
        待盘点池共 <b style={{ color: '#1677ff' }}>{poolItems.length}</b> 项，已选{' '}
        <b style={{ color: '#1677ff' }}>{poolSelectedIds.length}</b> 项
      </span>
      <Space>
        <Button
          disabled={poolSelectedIds.length === 0}
          onClick={() => {
            poolRemove(poolSelectedIds)
            setPoolSelectedIds([])
          }}
        >
          移除选中
        </Button>
        <Popconfirm
          title="确定清空待盘点池？"
          okText="确定"
          cancelText="取消"
          onConfirm={() => {
            poolClear()
            setPoolSelectedIds([])
          }}
        >
          <Button disabled={poolItems.length === 0}>清空</Button>
        </Popconfirm>
        <Button onClick={onCancel}>取消</Button>
        <Button type="primary" loading={confirmLoading} onClick={handlePoolCreate}>
          创建盘点单(已选{poolSelectedIds.length}项)
        </Button>
      </Space>
    </Space>
  )

  return (
    <Modal
      title="选择盘点物料"
      open={open}
      onCancel={onCancel}
      width={900}
      destroyOnClose
      footer={activeTab === 'search' ? searchFooter : poolFooter}
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as TabKey)}
        items={[
          { key: 'search', label: '搜索物料', children: searchTab },
          {
            key: 'pool',
            label: (
              <span data-tour="stock-check-pool-tab">
                待盘点池 ({poolItems.length})
              </span>
            ),
            children: poolTab,
          },
        ]}
      />
    </Modal>
  )
}
```

**Step 3.2: Verify the file compiles.**

From `frontend/`:
```bash
npm run build
```

Expected: a TS error from `index.tsx` because `handleCreateFromMaterials` (which is the function passed as `onConfirm`) still has the old `(selected: MaterialCandidate[])` signature. We fix that in Task 4.

---

## Task 4: Update `index.tsx` — pool badge, source flag, pool removal on success

**Files:**
- Edit: `frontend/src/pages/MaterialCenter/StockCheck/index.tsx`

**Step 4.1: Update imports.**

In the antd import block (line 3-6), add `Badge`:
```tsx
  Table, Input, Button, Space, Tag, message, Modal, Card, Row, Col,
  InputNumber, Checkbox, Spin, Popover, Tour, Drawer, Empty, Tooltip, DatePicker, Segmented, Badge,
```

After the existing `useUiPreferencesStore` import (line 11), add:
```tsx
import { useStockCheckPoolStore } from '@/store/stockCheckPool'
```

**Step 4.2: Subscribe to the pool count inside the component.**

Find the top of the `StockCheckPage` component (search for `export default function StockCheckPage` in `index.tsx`). Add this line just inside the component body (alongside the existing `useState` declarations):

```tsx
  const poolCount = useStockCheckPoolStore((s) => s.items.length)
  const poolRemove = useStockCheckPoolStore((s) => s.remove)
```

**Step 4.3: Update `handleCreateFromMaterials` to accept the source flag and remove used pool entries on success.**

Replace the existing `handleCreateFromMaterials` (currently `index.tsx:188-208`) with:

```tsx
  const handleCreateFromMaterials = useCallback(async (selected: MaterialCandidate[], source: 'search' | 'pool') => {
    setCreating(true)
    try {
      const res: any = await materialApi.createStockCheckFromMaterials({
        material_ids: selected.map((s) => s.erp_material_id),
      })
      const c: StockCheck = res.data
      message.success(`已创建手动盘点单 ${c.check_no}`)
      if (source === 'pool') {
        poolRemove(selected.map((s) => s.erp_material_id))
      }
      setPickerOpen(false)
      setActiveCheck(c)
      setItems(c.items || [])
      setOrderNo('')
      setCheckIdParam(c.id)
      setParams({ checkId: String(c.id) })
      reloadRecentList()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '创建盘点单失败')
    } finally {
      setCreating(false)
    }
  }, [reloadRecentList, setParams, poolRemove])
```

**Step 4.4: Wrap the manual-create trigger button with the pool badge and tour anchor.**

Replace the current manual-create block (currently `index.tsx:586-590`):

```tsx
        <span data-tour="stock-check-manual-create">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setPickerOpen(true)}>
            手动盘点 — 选择物料
          </Button>
        </span>
```

with:

```tsx
        <span data-tour="stock-check-manual-create">
          <span data-tour="stock-check-pool-badge">
            <Badge count={poolCount} size="small" offset={[10, -2]} overflowCount={999}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setPickerOpen(true)}>
                手动盘点 — 选择物料
              </Button>
            </Badge>
          </span>
        </span>
```

**Step 4.5: Verify.**

From `frontend/`:
```bash
npm run build
```
Expected: success.

---

## Task 5: Add a tour step for the pool badge

**Files:**
- Edit: `frontend/src/pages/MaterialCenter/StockCheck/StockCheckTour.tsx`

**Step 5.1: Add one step to `stockCheckIntroSteps`.**

In `frontend/src/pages/MaterialCenter/StockCheck/StockCheckTour.tsx`, append a fifth step to the `stockCheckIntroSteps` array (after the existing 4th step "4. 按类型筛选"). The new array reads:

```tsx
export const stockCheckIntroSteps: TourProps['steps'] = [
  {
    title: '1. 搜索订单',
    description: '按订单号搜索,自动加载该订单的盘点单(订单盘点模式入口)。',
    target: dataTour('search'),
  },
  {
    title: '2. 为订单创建盘点单',
    description: '未找到盘点单时点此按钮,按订单 BOM 自动展开物料建单 (订单模式专用)。',
    target: dataTour('create'),
  },
  {
    title: '3. 手动盘点 — 选择物料',
    description: '无需订单,从物料库任意选择要盘点的物料(支持搜索/多选/查看即时库存),适合周期盘点、抽盘、专项盘点。',
    target: dataTour('manual-create'),
  },
  {
    title: '4. 按类型筛选',
    description: '在最近盘点单列表中可切换:全部 / 订单盘点 / 手动盘点,快速定位历史记录。',
    target: dataTour('type-filter'),
  },
  {
    title: '5. 待盘点物料池(可选)',
    description:
      '按钮上的红色数字是你当前的待盘点物料池数量。多次搜索/不同关键词选到的物料可先加入池中,集中后再一次性创建盘点单;每次创建后只移除已使用的物料。',
    target: dataTour('pool-badge'),
  },
]
```

**Step 5.2: Add a `data-tour` anchor for the pool badge in `index.tsx`.**

(This is already done in Task 4.4 — the new `data-tour="stock-check-pool-badge"` `<span>` wraps the badge.) Confirm by re-reading Task 4.4.

**Step 5.3: Verify.**

From `frontend/`:
```bash
npm run build
```
Expected: success.

---

## Task 6: Final build verification

**Step 6.1: Run the full build one more time.**

From `frontend/`:
```bash
npm run build
```
Expected: clean success. This is the only typecheck per AGENTS.md.

**Step 6.2: Manual smoke checklist (no automation — verify in dev server).**

Start the dev server (`npm run dev` from `frontend/`) and the backend (`uvicorn app.main:app --reload --port 8000` from `backend/`) and confirm:

1. Log in -> click `手动盘点 — 选择物料`. The modal opens on Tab 1 `搜索物料`; no badge on the trigger button (pool empty).
2. Search a keyword -> check a few rows -> click `加入待盘点池(已选N项)`. Tab label changes to `待盘点池 (N)`. Close the modal -> reopen -> Tab 2 shows your materials; trigger button shows an `N` badge.
3. Re-open the modal -> Tab 2 -> click `移除选中` on one row -> that row is gone, the rest stay.
4. Tab 2 -> click `清空` -> confirm -> pool is empty, badge gone.
5. Re-populate pool across 2 different searches (e.g. different keywords). Tab 2 shows everything.
6. Tab 2 -> tick a subset (e.g. 3 of 5) -> click `创建盘点单(已选3项)`. A new盘点单 opens with exactly those 3 materials. Reopen picker -> Tab 2 shows the remaining 2 (auto-removed only the used ones).
7. Reload the page -> reopen picker -> Tab 2 still shows the remaining 2 (localStorage persistence).
8. Logout -> login as a different user -> reopen picker -> Tab 2 is empty (per-user scoping). Logout and re-login as the original user -> Tab 2 shows the 2 again.

**Step 6.3: Confirm no backend changes.**

Run:
```bash
git diff --stat -- backend/
```
Expected: empty output. (Frontend-only change.)