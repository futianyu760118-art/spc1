# 待盘点物料池 (Pending Stock-Check Material Pool) — Design

- **Date:** 2026-07-16
- **Status:** Draft, awaiting user review
- **Scope:** Frontend only (no backend / DB / schema changes)

## 1. Problem

手动盘点 (manual stock check) already supports multi-material selection (1–500 materials per
`POST /materials/stock-check/from-materials`, validated at `stock_check.py:73-74`). But the selection
happens in a **single** `MaterialPickerModal` session: open modal → search → select → confirm creates
the盘点单 immediately. If a user wants to gather materials from several different searches (or over
time) into one盘点单, there is no way to accumulate them — each confirm is a hard cut.

**Goal:** introduce a per-browser "待盘点物料池" (pending pool). Materials can be added across multiple
searches/sessions; later the user picks a subset and creates one盘点单 from the accumulated pool.

## 2. Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Where the pool lives | **Frontend-only, `localStorage`** (no backend table) |
| Entry point for adding | **Inside the existing `MaterialPickerModal`** only |
| Presentation | **Two tabs inside the modal**: `搜索物料` / `待盘点池 (N)` |
| After creating a盘点单 | **Auto-clear only the used (selected) materials** from the pool |
| Create from pool | **Subset-selectable** (checkboxes on the pool tab) |
| State management | **Zustand store with manual `localStorage`** (matches `uiPreferences.ts` convention — the repo does NOT use `zustand/middleware` `persist`) |
| Scoping | **Per-user**: localStorage key namespaced by current user id (`spc_stock_check_pool:<userId>`); each login gets its own pool |
| Extras | **Include now**: live-count badge on the `手动盘点` trigger button (§5.3) **and** one Tour step for the pool tab (§5.4) |

## 3. Non-goals (YAGNI)

- No server-side persistence, no cross-device / cross-user sharing.
- No multiple named pools — one pool per browser.
- No new backend endpoints, models, columns, or migrations.
- No add-to-pool buttons on other pages (material master, order detail, etc.) — only the picker.
- No TTL / expiry on pool entries.

## 4. Data model

A new Zustand store `frontend/src/store/stockCheckPool.ts`, following the `uiPreferences.ts` pattern
(manual `localStorage` read in creator, write in each mutator). **Per-user scoping**: the localStorage
key is namespaced as `spc_stock_check_pool:<userId>`, loaded via `loadForUser(userId)` — wired from
`auth.ts` `setAuth` (same pattern as `useUiPreferencesStore.loadFromUser`).

```ts
// frontend/src/store/stockCheckPool.ts
const STORAGE_KEY_PREFIX = 'spc_stock_check_pool'

function storageKeyFor(userId: number | null): string {
  return `${STORAGE_KEY_PREFIX}:${userId ?? 'anon'}`
}

function readLocal(key: string): PoolMaterial[] {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export interface PoolMaterial {
  erp_material_id: number   // unique dedup key (same as candidate row key)
  material_code: string | null
  material_name: string | null
  spec_model: string | null
  unit: string | null
  system_qty: number | null  // add-time snapshot, DISPLAY ONLY
  added_at: string           // ISO timestamp
}

interface StockCheckPoolState {
  items: PoolMaterial[]
  add: (materials: PoolMaterial[]) => void
  remove: (erpMaterialIds: number[]) => void
  clear: () => void
  has: (erpMaterialId: number) => boolean
  loadForUser: (userId: number | null) => void   // called from auth.ts setAuth / logout
  currentUserId: number | null
}
```

- **`loadForUser(userId)`**: reads `localStorage[spc_stock_check_pool:<userId>]` → sets `items` and `currentUserId`.
  Called from `auth.ts` `setAuth` (on login) and `logout` (pass `null` → in-memory items cleared, persisted per-user entry untouched).
- **Each mutator** (`add`, `remove`, `clear`) writes back to `localStorage` using `storageKeyFor(currentUserId)`.

- **Dedup:** `add()` merges by `erp_material_id`; re-adding an existing material is a no-op (the search
  tab will show those rows as "已在池中", disabled add button).
- **Snapshot vs live:** `system_qty` is an add-time snapshot for pool-tab display only. The actual
 盘点单 is always built from **live** stock — the existing `create_stock_check_from_materials`
  (`stock_check_service.py:156-232`) re-reads `scm_inventory.qty_on_hand` at create time. No backend
  change is needed to keep created盘点单 accurate.
- **Capacity:** bounded by the 500-material盘点单 limit at *create* time. The pool itself can exceed
  500 (user may create multiple盘点单 from one pool). If the user selects > 500 to create at once,
  the frontend blocks with a message before calling the API (the backend would reject anyway at
  `stock_check.py:73-74`).

## 5. UI changes

### 5.1 `MaterialPickerModal.tsx` — add Tabs

Current body is a flat search + table. Wrap it in antd `Tabs` with two panes:

**Tab 1 — `搜索物料`** (current search behavior, plus add-to-pool actions):
- Keep existing keyword search, table, pagination, per-row checkbox, "select all on page".
- **New per-row action** in an actions column: `加入待盘点池` (small button or `PlusOutlined` icon).
  Disabled + relabeled `已在池中` when the row's `erp_material_id` is already in the pool
  (checked via `useStockCheckPoolStore(s => s.has(id))` or a derived Set).
- **New batch button** in the footer alongside the existing `确定并创建盘点单`:
  `加入待盘点池(已选N项)`. Adds all currently-checked rows to the pool. **Does NOT close the modal**
  and does NOT clear the checkboxes — so the user can keep searching and accumulating.
- The existing `确定并创建盘点单` (immediate create from current selection) is **kept as-is** for
  users who want the old one-shot flow.
- Adding to pool shows a short `message.success('已加入待盘点池，当前共 X 项')`.

**Tab 2 — `待盘点池 (N)`** (N = live `items.length`, shown as a badge):
- Table columns: `物料编码` / `物料名称` / `规格` / `单位` / `即时库存(快照)` / `加入时间` / 操作.
- antd `rowSelection` (checkboxes) for subset selection — supports "select all", range, etc. for free.
- Per-row `移除` action.
- Footer toolbar: `移除选中` (secondary), `清空` (secondary, confirm-popconfirm), and primary
  `创建盘点单(选中N项)`.
- Empty state: antd `Empty` with hint `待盘点池为空，请到「搜索物料」标签添加物料`.

### 5.2 Create-from-pool flow

1. User selects a subset on Tab 2 (or all via header checkbox).
2. Click `创建盘点单(选中N项)`.
3. Frontend validates `1 ≤ selected.length ≤ 500`; else `message.warning`.
4. Call the **existing** `materialApi.createStockCheckFromMaterials({ material_ids: selectedErpIds })`
   — no new API. Reuses `handleCreateFromMaterials` logic already in `index.tsx:188-208`.
5. On success:
   - `pool.remove(selectedErpIds)` — auto-clear only used materials (per decision §2).
   - Close the modal.
   - Open the new盘点单 detail (identical to today's post-create behavior).
6. On error: keep the pool and selection intact, surface the error message.

### 5.3 `index.tsx` (StockCheckPage)

- Reuse the existing `onConfirm` handler path. The modal's `onConfirm(selected)` already drives
  `handleCreateFromMaterials`; the pool-tab create calls the same callback with the selected pool
  subset. Minimal change: pass a flag/origin if we want different success messaging, otherwise none.
- **Pool-count badge on the trigger button** (`index.tsx:586-590`): read `useStockCheckPoolStore`
  `items.length` and render a small antd `Badge` (zero-count hidden) on the `手动盘点 — 选择物料`
  button, so users can see they have pending materials before opening the picker.

### 5.4 `StockCheckTour.tsx`

- **Add one tour step** for the `manual-detail` tour (`STOCK_CHECK_MANUAL_DETAIL_TOUR_ID`) pointing
  at the `待盘点池` tab, explaining the accumulate-then-create workflow. This is included in the current
  change (not deferred).

## 6. Files touched

| File | Change | Risk |
|---|---|---|
| `frontend/src/store/stockCheckPool.ts` | **NEW** — Zustand store + manual localStorage, per-user keyed | Low (isolated) |
| `frontend/src/store/auth.ts` | **EDIT** — import pool store; call `loadForUser(user.id)` in `setAuth`, call `loadForUser(null)` in `logout` | Low (same pattern as theme/perm/uiPref) |
| `frontend/src/pages/MaterialCenter/StockCheck/MaterialPickerModal.tsx` | **EDIT** — wrap in Tabs, add pool tab, add-to-pool actions, create-from-pool | Medium (core component) |
| `frontend/src/pages/MaterialCenter/StockCheck/index.tsx` | **EDIT** — pool-count Badge on trigger button; ensure pool-create reuses `handleCreateFromMaterials` | Low |
| `frontend/src/pages/MaterialCenter/StockCheck/StockCheckTour.tsx` | **EDIT** — add one tour step for `待盘点池` tab | Low |

**No backend files. No `init_database.py`. No models / schemas / API.**

## 7. Edge cases & behavior

- **Login / logout / user-switch:** pool is keyed per user (`spc_stock_check_pool:<userId>`). On login,
  `auth.ts` `setAuth` calls `useStockCheckPoolStore.getState().loadForUser(user.id)`, which reads the
  correct per-user localStorage entry and sets in-memory `items`. On logout, `loadForUser(null)` clears
  in-memory items (the persisted per-user entry remains untouched, so the pool survives re-login by
  the same user). If user A logs out and user B logs in on the same browser, user B sees B's pool —
  no cross-contamination.
- **Material deleted/disabled after being pooled:** the pool entry is just a display snapshot. At
  create time, `create_stock_check_from_materials` filters to `is_deleted=0`
  (`stock_check_service.py:183`) and raises if zero valid materials remain. The frontend will surface
  that error; the user can remove the stale entry manually. No proactive sync.
- **`system_qty` drift:** display snapshot may lag live stock. Acceptable — the created盘点单 uses live
  values. The pool tab column header is labeled `即时库存(快照)` to set expectations.
- **Pool exceeds 500:** allowed in the pool; only the *selected-for-create* set is capped at 500.
- **Browser private mode / disabled localStorage:** wrap reads in try/catch (as `uiPreferences.ts`
  does); the pool simply won't persist — the feature degrades to in-memory (lost on reload).

## 8. Verification

Per AGENTS.md, `npm run build` (from `frontend/`) is the only typecheck and must pass. There is no
test suite. Manual verification:
1. `npm run build` passes.
2. Open `手动盘点` picker → search → add several rows to pool across 2–3 different searches; confirm
   the Tab 2 badge count updates and dedup works (already-added rows show `已在池中`).
3. Reload the page → reopen picker → Tab 2 still shows the accumulated pool (localStorage persistence).
4. Select a subset on Tab 2 → `创建盘点单` → confirm a new盘点单 opens with exactly those materials,
   and the selected entries are removed from the pool (unselected remain).
5. Select > 500 → confirm the frontend blocks before calling the API.
6. Logout → login → pool still present (per-browser).

## 9. Open questions

_Resolved in brainstorming session 2026-07-16:_ both the badge + tour step and per-user scoping are
included in this design (see §2 and §5.3/§5.4).
