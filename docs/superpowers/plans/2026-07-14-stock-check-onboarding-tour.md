# 物料盘点新手指引 (Stock Check Onboarding Tour) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an `antd.Tour` walkthrough on the StockCheck page that auto-shows for first-time users, re-triggerable via a "?" help button, with state persisted via the existing `sys_user.ui_preferences` JSONB column. No backend changes.

**Architecture:** Frontend-only. Extend `useUiPreferencesStore` with 2 generic methods (`getFlag` / `setFlag`) that reuse the existing localStorage + `authApi.updatePreferences` sync pattern. Add a new `StockCheckTour.tsx` step config file. Integrate `antd.Tour` in `StockCheck/index.tsx` with `data-tour` attribute anchors on 5 key DOM elements. Add a "?" help button (with a Popover that includes a global newbie-mode toggle) next to the search bar.

**Tech Stack:** Ant Design 5 (`Tour` + `Popover` + `Checkbox`), Zustand (`useUiPreferencesStore`), React 18 (`useRef` + `useEffect`). Zero new dependencies.

## Global Constraints

- `npm run build` (i.e. `tsc -b && vite build`) is the **only** typecheck (per AGENTS.md).
- The frontend axios interceptor (`frontend/src/services/api.ts`) treats `response.data.code !== 0` as a failure.
- All response envelopes must be `ResponseModel[T]` from `backend/app/schemas/common.py` — not relevant for this task (no backend changes).
- Add comments only when explicitly requested.

---

## Task 1: Extend `useUiPreferencesStore` with `getFlag` / `setFlag`

**Files:**
- Modify: `frontend/src/store/uiPreferences.ts`

**Step 1: Add the 2 methods to the store interface and implementation**

Edit `D:\wanghuazheng\project\SPC-v2\frontend\src\store\uiPreferences.ts`:

Replace the interface block (lines 4-9):

```ts
interface UiPreferencesState {
  preferences: Record<string, any>
  getColumnVisibility: (pageKey: string, defaultColumns: string[]) => string[]
  setColumnVisibility: (pageKey: string, visibleColumns: string[]) => void
  loadFromUser: (user: any) => void
  getFlag: (key: string, defaultValue?: any) => any
  setFlag: (key: string, value: any) => void
}
```

Insert the new methods inside the returned object, after `setColumnVisibility` (i.e. between the `setColumnVisibility` block and the `loadFromUser` block, around line 48):

```ts
    getFlag: (key, defaultValue = false) => {
      const v = get().preferences[key]
      return v === undefined ? defaultValue : v
    },

    setFlag: (key, value) => {
      const next = { ...get().preferences, [key]: value }
      set({ preferences: next })
      localStorage.setItem(UI_PREFS_KEY, JSON.stringify(next))
      authApi.updatePreferences({ ui_preferences: next }).catch((err: Error) => {
        console.error(`Failed to save UI flag [${key}]:`, err)
      })
    },
```

The final file should look like (full content):

```ts
import { create } from 'zustand'
import { authApi } from '../services/api'

interface UiPreferencesState {
  preferences: Record<string, any>
  getColumnVisibility: (pageKey: string, defaultColumns: string[]) => string[]
  setColumnVisibility: (pageKey: string, visibleColumns: string[]) => void
  loadFromUser: (user: any) => void
  getFlag: (key: string, defaultValue?: any) => any
  setFlag: (key: string, value: any) => void
}

const UI_PREFS_KEY = 'spc_ui_preferences'

function readLocalPrefs(): Record<string, any> {
  try {
    const raw = localStorage.getItem(UI_PREFS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export const useUiPreferencesStore = create<UiPreferencesState>((set, get) => {
  const initial = readLocalPrefs()

  return {
    preferences: initial,

    getColumnVisibility: (pageKey, defaultColumns) => {
      const prefs = get().preferences
      const page = prefs[pageKey]
      if (page && Array.isArray(page.visibleColumns)) {
        return page.visibleColumns
      }
      return defaultColumns
    },

    setColumnVisibility: (pageKey, visibleColumns) => {
      const next = {
        ...get().preferences,
        [pageKey]: { ...get().preferences[pageKey], visibleColumns },
      }
      set({ preferences: next })
      localStorage.setItem(UI_PREFS_KEY, JSON.stringify(next))

      authApi.updatePreferences({ ui_preferences: next }).catch((err: Error) => {
        console.error('Failed to save column visibility preference:', err)
      })
    },

    getFlag: (key, defaultValue = false) => {
      const v = get().preferences[key]
      return v === undefined ? defaultValue : v
    },

    setFlag: (key, value) => {
      const next = { ...get().preferences, [key]: value }
      set({ preferences: next })
      localStorage.setItem(UI_PREFS_KEY, JSON.stringify(next))
      authApi.updatePreferences({ ui_preferences: next }).catch((err: Error) => {
        console.error(`Failed to save UI flag [${key}]:`, err)
      })
    },

    loadFromUser: (user) => {
      if (user?.ui_preferences && typeof user.ui_preferences === 'object') {
        const merged = { ...readLocalPrefs(), ...user.ui_preferences }
        localStorage.setItem(UI_PREFS_KEY, JSON.stringify(merged))
        set({ preferences: merged })
      }
    },
  }
})
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npx tsc --noEmit -p tsconfig.json 2>&1 | Select-String "uiPreferences" | Select-Object -First 5
```
Expected: no TypeScript errors related to uiPreferences.

---

## Task 2: Create tour steps config file

**Files:**
- Create: `frontend/src/pages/OrderDelivery/StockCheck/StockCheckTour.tsx`

**Step 1: Create the tour config file**

Create `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\OrderDelivery\StockCheck\StockCheckTour.tsx`:

```tsx
import type { TourProps } from 'antd'

export const STOCK_CHECK_TOUR_ID = 'stock_check'

function dataTour(name: string): () => HTMLElement | null {
  return () => document.querySelector<HTMLElement>(`[data-tour="stock-check-${name}"]`)
}

export const stockCheckTourSteps: TourProps['steps'] = [
  {
    title: '1. 搜索订单',
    description: '按订单号搜索,自动加载该订单的盘点单。',
    target: dataTour('search'),
  },
  {
    title: '2. 创建盘点单',
    description: '未找到盘点单时,点此按钮按订单的 BOM 自动展开物料建单。',
    target: dataTour('create'),
  },
  {
    title: '3. 物料表的三个数',
    description: '应盘数=订单需求,库存数=系统当前库存(qty_on_hand),盘点数=你录入的实盘。',
    target: dataTour('table'),
  },
  {
    title: '4. 差异列',
    description: '差异自动算出:盘点数 - 库存数。正数盘盈,负数盘亏。',
    target: dataTour('diff'),
  },
  {
    title: '5. 操作按钮',
    description: '保存全部 → 批量提交;标记完成 → 完结(需所有行都已盘点);取消 → 终止盘点单。',
    target: dataTour('actions'),
  },
]
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npx tsc --noEmit -p tsconfig.json 2>&1 | Select-String "StockCheckTour" | Select-Object -First 5
```
Expected: no errors.

---

## Task 3: Integrate `antd.Tour` + `?` button + `data-tour` anchors in StockCheck page

**Files:**
- Modify: `frontend/src/pages/OrderDelivery/StockCheck/index.tsx`

**Step 1: Add imports and tour-related state**

In `frontend/src/pages/OrderDelivery/StockCheck/index.tsx`, modify the imports block at the top (currently lines 1-15):

Add to the `antd` import group:
```tsx
import {
  Table, Input, Button, Space, Tag, message, Modal, Card, Row, Col,
  InputNumber, Checkbox, Spin, Popover, Tour,
} from 'antd'
```

Add `@ant-design/icons` import (find existing icon import block and append `QuestionCircleOutlined`):
```tsx
import { SearchOutlined, ReloadOutlined, CheckCircleOutlined, StopOutlined, ArrowLeftOutlined, SaveOutlined, QuestionCircleOutlined } from '@ant-design/icons'
```

Add new imports at the bottom of the import block:
```tsx
import { useRef } from 'react'
import { useUiPreferencesStore } from '@/store/uiPreferences'
import { stockCheckTourSteps, STOCK_CHECK_TOUR_ID } from './StockCheckTour'
```

**Step 2: Add tour state and refs inside the component**

Inside `StockCheckPage()` component, after the existing state declarations (after the `const [savingAll, setSavingAll] = useState(false)` line, around line 65), insert:

```tsx
  const tourRef = useRef<any>(null)
  const [tourOpen, setTourOpen] = useState(false)
  const newbieMode = useUiPreferencesStore(s => s.preferences?.newbie_mode !== false)
  const seenTours = useUiPreferencesStore(s => s.preferences?.['tours_seen'] ?? {})
  const setUiFlag = useUiPreferencesStore(s => s.setFlag)
```

Add the auto-trigger effect (after the existing `useEffect` blocks, before the `saveItem` callback):

```tsx
  useEffect(() => {
    if (!newbieMode) return
    if (seenTours?.[STOCK_CHECK_TOUR_ID]) return
    const t = setTimeout(() => {
      setTourOpen(true)
    }, 500)
    return () => clearTimeout(t)
  }, [newbieMode, seenTours])

  const handleTourClose = useCallback(() => {
    const current = useUiPreferencesStore.getState().getFlag('tours_seen', {})
    useUiPreferencesStore.getState().setFlag('tours_seen', { ...current, [STOCK_CHECK_TOUR_ID]: true })
    setTourOpen(false)
  }, [])

  const handleHelpClick = useCallback(() => {
    setTourOpen(true)
  }, [])

  const handleNewbieToggle = useCallback((checked: boolean) => {
    setUiFlag('newbie_mode', checked)
  }, [setUiFlag])
```

**Step 3: Add `data-tour` attributes to the search section**

Find the `renderSearch()` function. Add `data-tour` to the search bar `<div>`:

Change the search div to:
```tsx
  const renderSearch = () => (
    <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
      <Space wrap>
        <span data-tour="stock-check-search">
          <Input
            placeholder="输入订单号 (如 HJ2024-001)"
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            onPressEnter={handleSearch}
            allowClear
            style={{ width: 280 }}
            prefix={<SearchOutlined />}
          />
        </span>
        <Button type="primary" onClick={handleSearch}>搜索订单</Button>
        <Button onClick={() => { setSearchText(''); setOrderNo(''); setActiveCheck(null); setItems([]); setParams({}) }}>清空</Button>
        {orderNo && !activeCheck && (
          <span data-tour="stock-check-create">
            <Button type="primary" ghost onClick={() => handleCreate(orderNo)} loading={loading}>
              为 {orderNo} 创建盘点单
            </Button>
          </span>
        )}
        <Popover
          trigger="click"
          placement="bottomRight"
          content={
            <div style={{ width: 200 }}>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>新手指引</div>
              <Button type="link" size="small" onClick={handleHelpClick} style={{ padding: 0, marginBottom: 8 }}>
                ▶ 立即查看
              </Button>
              <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 8 }}>
                <Checkbox checked={newbieMode} onChange={e => handleNewbieToggle(e.target.checked)}>
                  开启新手指引
                </Checkbox>
              </div>
            </div>
          }
        >
          <Button icon={<QuestionCircleOutlined />} shape="circle" title="新手指引" />
        </Popover>
      </Space>
    </div>
  )
```

**Step 4: Add `data-tour` attribute to the materials table**

In the "active check" detail view, find the Spin wrapping the materials Table. Add `data-tour` to the inner `<div>` around the Table:

Change:
```tsx
          <div className="card-modern" style={{ padding: 4 }}>
            <Spin spinning={loading}>
              <Table
                rowKey="id"
                dataSource={items}
                columns={columns}
                pagination={{ pageSize: 50, showSizeChanger: true, showTotal: t => `共 ${t} 项` }}
                scroll={{ x: 1600, y: 600 }}
                size="small"
              />
            </Spin>
          </div>
```

To (add data-tour="stock-check-table"):
```tsx
          <div className="card-modern" style={{ padding: 4 }} data-tour="stock-check-table">
            <Spin spinning={loading}>
              <Table
                rowKey="id"
                dataSource={items}
                columns={columns}
                pagination={{ pageSize: 50, showSizeChanger: true, showTotal: t => `共 ${t} 项` }}
                scroll={{ x: 1600, y: 600 }}
                size="small"
              />
            </Spin>
          </div>
```

**Step 5: Add `data-tour` attribute to the "差异" column header and the action buttons**

Find the `columns` `useMemo` block. Inside, find the column with `title: '差异'`. Add `data-tour` to the title:

Change:
```tsx
    {
      title: '差异', dataIndex: 'diff_qty', width: 90, align: 'right' as const,
      render: (v: any) => {
```

To:
```tsx
    {
      title: <span data-tour="stock-check-diff">差异</span>, dataIndex: 'diff_qty', width: 90, align: 'right' as const,
      render: (v: any) => {
```

Find the action buttons row in the active check header. Find this:
```tsx
              <Col span={6} style={{ textAlign: 'right' }}>
                <Space wrap>
                  <Button icon={<SaveOutlined />} onClick={saveAll} loading={savingAll} disabled={readonly}>
                    保存全部
                  </Button>
                  <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleComplete} disabled={readonly}>
                    标记完成
                  </Button>
                  <Button danger icon={<StopOutlined />} onClick={handleCancel} disabled={readonly}>
                    取消
                  </Button>
                </Space>
              </Col>
```

Wrap with `data-tour`:
```tsx
              <Col span={6} style={{ textAlign: 'right' }} data-tour="stock-check-actions">
                <Space wrap>
                  <Button icon={<SaveOutlined />} onClick={saveAll} loading={savingAll} disabled={readonly}>
                    保存全部
                  </Button>
                  <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleComplete} disabled={readonly}>
                    标记完成
                  </Button>
                  <Button danger icon={<StopOutlined />} onClick={handleCancel} disabled={readonly}>
                    取消
                  </Button>
                </Space>
              </Col>
```

**Step 6: Add the `<Tour>` component at the end of the page render**

Find the closing of the main return statement. Just before the final `</div>`, add:

```tsx
      <Tour
        open={tourOpen}
        steps={stockCheckTourSteps}
        onClose={handleTourClose}
        onFinish={handleTourClose}
      />
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npx tsc --noEmit -p tsconfig.json 2>&1 | Select-String "StockCheck|Tour" | Select-Object -First 10
```
Expected: zero errors (or only pre-existing unrelated warnings).

---

## Task 4: Final build + smoke verification

**Step 1: Run full build**

```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npm run build
```

Expected: `tsc -b && vite build` both succeed. The "Some chunks are larger than 500 kB" warning is pre-existing and unrelated.

**Step 2: Manual smoke test (optional)**

1. Start dev server: `npm run dev`
2. Login as admin
3. Navigate to an order with materials, click "盘点" button
4. Verify the StockCheck page loads
5. After 500ms, verify the tour auto-appears with 5 steps
6. Walk through all 5 steps, click "完成"
7. Refresh the page, verify the tour does NOT auto-appear
8. Click the "?" button in the search bar
9. Verify the tour re-appears
10. Click the "?" button, then uncheck "开启新手指引"
11. Refresh the page, verify the tour does NOT auto-appear

---

## Done criteria

- [ ] `npm run build` passes (tsc -b + vite build)
- [ ] 5 `data-tour` attributes present in StockCheck/index.tsx
- [ ] `<Tour>` component rendered with `stockCheckTourSteps`
- [ ] `?` button with Popover in search bar
- [ ] `getFlag` / `setFlag` added to `useUiPreferencesStore`
- [ ] No `orders.inventory_check` / old inventory check code is touched (this task is purely additive)
- [ ] No new files in `backend/` (frontend-only)
