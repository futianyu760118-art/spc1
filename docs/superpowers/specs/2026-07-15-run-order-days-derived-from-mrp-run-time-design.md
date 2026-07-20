# Design: 跑单时间(天) derived from `mrp_plan_order.mrp_run_time` − 下单时间

**Date:** 2026-07-15
**Status:** Approved
**Scope:** `订单交付中心 > 跑单管理` — the `run_days` (跑单时间(天)) field is redefined to be derived at read time from `MIN(mrp_plan_order.mrp_run_time) − po_placed_date`, measured in whole days. Mirrors the `run_date` derivation approved in the 2026-07-13 spec; reuses the same `_mrp_min_run_time` subquery.

**Builds on:** [2026-07-13-run-order-date-from-mrp-run-time-design.md](./2026-07-13-run-order-date-from-mrp-run-time-design.md) — which derived `run_date` and listed "auto-computing `run_days` from `run_date`" as out-of-scope (YAGNI). This spec promotes that YAGNI item to in-scope.

---

## 1. Background & current behavior

`RunOrder.run_days` (`Integer`, comment "跑单时间(天)") is a stored, manually-editable field today. It is populated three ways, none of which touch `mrp_plan_order` or `po_placed_date`:

- `sync_from_order` (`app/api/v1/order/run_order.py:211`) — leaves `run_days = NULL`.
- CSV import (`app/services/order/import_csv.py:226, 250, 272`) — from the "跑单时间" CSV column.
- Manual create/edit via the UI (inline-editable cell + create/edit modals).

The user requirement: **跑单时间 = 下单时间到 `mrp_plan_order.mrp_run_time` 之间的天数**.

Inputs (already present in the existing `list_run_orders` / `get_run_order` row tuple):
- `mrp_run_time` — `DateTime` from `_mrp_min_run_time` subquery (`MIN(mrp_plan_order.mrp_run_time) per order_no`), already used to derive `run_date`.
- `po_placed_date` — `Date` from `SaleOrder.order_date` (下单时间). Already selected on the row.

### Decisions (confirmed with user)

1. **Aggregation = `MIN(mrp_run_time)`** — same as `run_date`. The earliest MRP run time defines "跑单开始" and is the natural anchor for the day-delta.
2. **Formula = `(MIN(mrp_run_time).date() − po_placed_date).days`** — whole-day delta; `Date`−`Date` → `int` in Python's `datetime` semantics. **Negative values are allowed** (e.g. when MRP was re-run retroactively). `NULL` when either side is `NULL` (front-end renders as `-`).
3. **Timing = read-time, forced** — like `run_date`, the stored `run_order.run_days` is **ignored for display**. API computes and overwrites on every read.
4. **Calculation location = Python (post-fetch)** — keeps the change symmetric with the existing `run_date_val` calculation; no SQL date-dialect concerns.

---

## 2. SQL strategy

No new subquery. Reuse the existing `_mrp_min_run_time` derived table from the 2026-07-13 spec (`backend/app/api/v1/order/run_order.py:19-27`):

```python
_mrp_min_run_time = (
    select(
        SaleOrder.order_no.label("order_no"),
        func.min(MrpPlanOrder.mrp_run_time).label("mrp_run_time"),
    )
    .join(MrpPlanOrder, MrpPlanOrder.sale_order_id == SaleOrder.id)
    .group_by(SaleOrder.order_no)
    .subquery()
)
```

`po_placed_date` is already selected into the row tuple via `po_placed_date=sale_order.order_date` (`run_order.py:157`).

### Sort expression for `run_days`

The existing sort mapping (`run_order.py:36-39`) currently maps `'run_days'` → `RunOrder.run_days` (the stored value). After this change, the stored value is ignored. To keep sort order consistent with the displayed value, remap `'run_days'` to a SQL-side date-delta expression. PostgreSQL's `date − date` directly returns the integer day delta (matching Python's `(date_a − date_b).days` semantics — positive when `a > b`, negative when `a < b`, no timezone surprises):

```python
_mrp_min_run_time_days = (
    (func.date(_mrp_min_run_time.c.mrp_run_time) - SaleOrder.order_date)
    .label("mrp_run_days")
)
```

This is added to the main `select(...)` and used as the sort key for `run_days`. Because `date − date` is already an `int`, no `EXTRACT` / `EPOCH` conversion is needed (and `EXTRACT(DAY FROM AGE(...))` would be wrong here — it returns the `day` field of an `interval`, not the total day delta).

> **Alternative considered:** computing the delta in Python and post-sorting. Rejected — N rows × O(N log N) sort is wasteful when DB can do it; would also lose pagination semantics.

---

## 3. Code changes

### 3.1 Backend — `backend/app/api/v1/order/run_order.py`

#### Imports
No new imports required. The new sort expression only uses `func.date(...)` (already imported) and the `−` operator between SQLAlchemy column expressions.

#### Module-level subquery
The `_mrp_min_run_time` subquery is already module-local to `list_run_orders`. Promote it to module-level (or a small helper) so the sort expression and the row loop both reference the same subquery. (Today the subquery is built inside `list_run_orders`; the sort mapping dict is also inside the function. Keep the structure, but make sure `_mrp_min_run_time` is constructed before `RUN_ORDER_SORTABLE_COLUMNS` is resolved.)

#### `list_run_orders`
- Add `_mrp_min_run_time_days` to the `select(...)` projection (next to `mrp_run_time`).
- Add the alias to the row loop:
  ```python
  mrp_run_time = row.mrp_run_time
  po_placed_date = row.po_placed_date
  run_date_val = mrp_run_time.date() if mrp_run_time else None
  run_days_val = (
      (mrp_run_time.date() - po_placed_date).days
      if (mrp_run_time and po_placed_date) else None
  )
  ```
- In **both** branches (synced / un-synced), set `item.run_days = run_days_val`. This overrides the value populated by `RunOrderOut.model_validate(...)`.
- Sort mapping fix: `'run_days': _mrp_min_run_time_days` instead of `'run_days': RunOrder.run_days`.

#### `get_run_order`
- Currently selects `RunOrder` + joins `_mrp_min_run_time`. Extend the projection to also select `SaleOrder.order_date` (aliased as `po_placed_date` for symmetry with list query).
- After building the output, set:
  ```python
  out.run_date = mrp_run_time.date() if mrp_run_time else None
  out.run_days = (
      (mrp_run_time.date() - po_placed_date).days
      if (mrp_run_time and po_placed_date) else None
  )
  ```
  (matches the `run_date` override on the next line, which is already in the file).

#### Sort mapping location
The `RUN_ORDER_SORTABLE_COLUMNS` dict is built inside `list_run_orders`. After the change, `'run_days'` must point at the new SQL expression. The other `'run_date'` mapping already points at `_mrp_min_run_time.c.mrp_run_time` per the 2026-07-13 spec — leave it.

### 3.2 Frontend — `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx`

- **跑单时间(天) column** (~line 405-407): replace `editableNumber('run_days')` with a read-only render mirroring the 跑单日期 column's pattern:
  ```tsx
  {
    title: '跑单时间(天)',
    dataIndex: 'run_days',
    key: 'run_days',
    width: 110,
    sorter: true,
    render: (v: number | null | undefined) => (v === null || v === undefined ? '-' : v),
  }
  ```
  Rationale: stored value is ignored by the backend; editing would silently no-op on display. Keep `sorter: true` (backend sort now uses the SQL date-delta expression).
- **Create modal `run_days` Form.Item** (~line 594-597) and **Edit modal `run_days` Form.Item** (~line 713-716): set `disabled` and add a `tooltip="自动计算自 MRP 运算时间 − 下单时间"`. Mirrors the existing `run_date` Form.Item changes from the 2026-07-13 spec.

### 3.3 Out of scope (YAGNI)

- AI tool `search_run_orders` (`app/services/assistant/tools/search_run_orders.py`) — still reads stored `RunOrder.run_date` and `RunOrder.run_days`. Out of scope; the assistant cards already display 跑单日期 and 跑单天数 but a follow-up spec would need to mirror the read-time derivation in the tool's manual query.
- Removing `run_days` from `RunOrderCreate` / `RunOrderUpdate` schemas — kept to avoid breaking the form binding; UI just disables input.
- Migrating/clearing existing `run_order.run_days` rows — untouched (simply unused for display).
- CSV import (`app/services/order/import_csv.py`) — still writes to `run_order.run_days`. No-op for display; the column is ignored.
- A computed `run_days` materialized column on `RunOrder` or `MrpPlanOrder` — derivable on demand, not worth storing.

---

## 4. Consequences

- Orders with no `mrp_plan_order` data → `run_date = NULL` AND `run_days = NULL` (front-end renders `-`).
- Orders with no `po_placed_date` (下单时间 not synced) → `run_days = NULL` even if MRP data exists.
- `run_days` can be **negative** when MRP was re-run after the order was placed (e.g. retroactive MRP re-computation). This is by design; do not clamp to 0.
- Sort by 跑单时间(天) uses the SQL-side `date − date` expression — identical to the Python-side `(date - date).days` for whole-day precision.
- No schema migration needed — no new columns, no `init_database.py` change. Pure query + UI change.
- ERP sync of `mrp_plan_order` (existing `sync_mrp_plan_orders`) is the data source; no change to sync logic.

---

## 5. Verification

- `npm run build` (frontend, the only typecheck) passes.
- Start uvicorn, open 跑单管理, confirm 跑单时间(天) = `MRP 最早运算日期 − 下单时间` for a sample of orders (sanity-check by hand).
- Spot-check edge cases:
  - Order with no MRP data → 跑单时间 = `-`.
  - Order with no `po_placed_date` (下单时间未同步) → 跑单时间 = `-`.
  - Order where MRP was re-run after 下单时间 → 跑单时间 = negative integer.
- Sort by 跑单时间 ascending/descending — order matches the displayed values.
- 跑单时间 cell is read-only in the table (no inline edit pencil).
- Create/Edit modal — 跑单时间 field is disabled with the tooltip "自动计算自 MRP 运算时间 − 下单时间".

---

## 6. File reference index

| File | Purpose of change |
|------|-------------------|
| `backend/app/api/v1/order/run_order.py:1-50` | Imports + subquery construction |
| `backend/app/api/v1/order/run_order.py:48-180` | `list_run_orders` row loop adds `run_days_val` override + sort mapping |
| `backend/app/api/v1/order/run_order.py:183-201` | `get_run_order` adds `run_days` override |
| `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx:405-407` | 跑单时间(天) column → read-only |
| `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx:594-597` | Create modal `run_days` Form.Item → `disabled` + tooltip |
| `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx:713-716` | Edit modal `run_days` Form.Item → `disabled` + tooltip |
