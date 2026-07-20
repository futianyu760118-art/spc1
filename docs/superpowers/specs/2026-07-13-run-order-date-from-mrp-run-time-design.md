# Design: 跑单日期 derived from `mrp_plan_order.mrp_run_time`

**Date:** 2026-07-13
**Status:** Approved
**Scope:** `订单交付中心 > 跑单管理` — the `run_date` (跑单日期) field is redefined to be derived at read time from `MIN(mrp_plan_order.mrp_run_time)` per order.

---

## 1. Background & current behavior

`RunOrder.run_date` (`Date`) is a stored, manually-editable field today. It is populated three ways, none of which touch `mrp_plan_order`:

- `sync_from_order` (`app/api/v1/order/run_order.py:211`) — leaves `run_date = NULL`.
- CSV import (`app/services/order/import_csv.py`) — from the "跑单日期" CSV column.
- Manual create/edit via the UI (inline-editable cell + create/edit modals).

The user requirement: **跑单日期 取自 `mrp_plan_order.mrp_run_time`**.

`mrp_plan_order.mrp_run_time` (`DateTime`, comment "MRP运算时间") is synced from ERP (`init_database.py:1349` maps `mr.FDate`). It is per (sale_order_id, material_id) row.

### Data model & join path

- `mrp_plan_order`: composite PK `(sale_order_id, material_id)`; `sale_order_no` is **nullable**, so the reliable join is via `sale_order_id → sale_order.id`.
- `sale_order`: unique on `(order_no, line_no)` — one `order_no` spans **multiple** `sale_order` rows (lines).
- `run_order`: unique on `order_no`.

Therefore one `order_no` → many `sale_order.id` → many `mrp_plan_order` rows → **many `mrp_run_time` values**. Aggregation is required.

### Decisions (confirmed with user)

1. **Aggregation = `MIN(mrp_run_time)`** — earliest MRP run time = when the order first entered MRP. Matches "跑单开始" semantics.
2. **Timing = read-time, forced** — `run_date` is always `MIN(mrp_run_time)::date` at query time. The stored `run_order.run_date` is **ignored for display**. If no `mrp_plan_order` row exists for the order, `run_date = NULL`.

---

## 2. SQL strategy — Approach A: grouped subquery + LEFT JOIN

A derived table computing `MIN(mrp_run_time)` per `order_no`, LEFT JOINed into the existing list/detail queries.

```python
mrp_min = (
    select(
        SaleOrder.order_no.label("order_no"),
        func.min(MrpPlanOrder.mrp_run_time).label("mrp_run_time"),
    )
    .join(MrpPlanOrder, MrpPlanOrder.sale_order_id == SaleOrder.id)
    .group_by(SaleOrder.order_no)
    .subquery()
)
```

Main query gains: `.outerjoin(mrp_min, mrp_min.c.order_no == SaleOrder.order_no)` and selects `mrp_min.c.mrp_run_time`.

Output: `run_date = mrp_min.mrp_run_time.date() if val else None` (DateTime → Date cast, matches `RunOrderOut.run_date: Optional[date]`).

Rejected alternatives:
- **Correlated scalar subquery** — per-row execution; awkward to sort on (must duplicate expression).
- **DB view** — overkill.

---

## 3. Code changes

### 3.1 Backend — `backend/app/api/v1/order/run_order.py`

Add `from app.models.material.mrp_plan_order import MrpPlanOrder` import.

#### `list_run_orders`
- Build the `mrp_min` subquery (above).
- Add `mrp_min.c.mrp_run_time` to the `select(...)`.
- Add `.outerjoin(mrp_min, mrp_min.c.order_no == SaleOrder.order_no)` to both the data query **and** the count query is unaffected (count is on `SaleOrder.id.distinct()`, no need to join mrp_min for counting). Filters that reference `RunOrder` columns (order_status, is_domestic) remain on the existing `RunOrder` join.
- In the row loop:
  - Synced branch (`run_order` exists): set `item.run_date = row.mrp_run_time.date() if row.mrp_run_time else None` (override the model-validated value).
  - Un-synced branch: same — `run_date = row.mrp_run_time.date() if row.mrp_run_time else None` (was `None`).
- **Sort mapping fix:** `RUN_ORDER_SORTABLE_COLUMNS['run_date']` currently maps to `RunOrder.run_date` (the now-ignored stored value). Repoint it to `mrp_min.c.mrp_run_time` so sort order matches the displayed value. Implementation note: the sort column is looked up before the query is built, so the `mrp_min` subquery must be constructed before the sort-column resolution, or the mapping value changed to reference `mrp_min.c.mrp_run_time` directly. Simplest: replace the dict entry's value at query time (the subquery is module-level-ish per call). Concretely, build `mrp_min` at the top of the function and use a local sort lookup that substitutes `'run_date' → mrp_min.c.mrp_run_time`.

#### `get_run_order`
- Currently: `select(RunOrder).where(RunOrder.id == run_order_id)`.
- Change to also fetch the derived `mrp_run_time`: join `run_order → sale_order` (on `order_no`) → `mrp_min` (on `order_no`). Set `run_date` on the output from `mrp_min.mrp_run_time`.
- Keep the 404 check on `run_order` existence.

### 3.2 Frontend — `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx`

- `跑单日期` column (`run_date`, ~line 401): change `render: editableDate('run_date')` → plain read-only date render (e.g. `render: (v) => v || '-'`). Rationale: stored value is ignored by the backend; editing would silently no-op on display. Keep `sorter: true`.
- `跑单时间(天)` (`run_days`, ~line 405): **unchanged** — stays `editableNumber` (still a stored, manual field).
- Create modal `run_date` Form.Item (~line 589) and Edit modal `run_date` Form.Item (~line 708): set `disabled` (the value is derived; keeping the field avoids schema churn but prevents confusing input). Add a hint text "自动取自 MRP 运算时间".

### 3.3 Out of scope (YAGNI)
- `search_run_orders` assistant tool (`app/services/assistant/tools/search_run_orders.py`) — still reads stored `RunOrder.run_date`. Follow-up if needed.
- Auto-computing `run_days` from `run_date` — not requested.
- Removing `run_date` from `RunOrderCreate` / `RunOrderUpdate` schemas — kept to avoid breaking the form binding; UI just disables input.
- Migrating/clearing existing `run_order.run_date` rows — untouched (simply unused for display).

---

## 4. Consequences

- Orders with no `mrp_plan_order` data show `run_date = NULL`, even if a manual `run_order.run_date` was previously set (by design — "forced" derivation).
- `mrp_run_time` is `DateTime`; output truncated to `Date`.
- Sorting by `跑单日期` now sorts by the derived `MIN(mrp_run_time)`, consistent with display.
- No schema migration needed — no new columns, no `init_database.py` change. Pure query + UI change.
- ERP sync of `mrp_plan_order` (existing `sync_mrp_plan_orders`) is the data source; no change to sync logic.

---

## 5. Verification

- `npm run build` (frontend, the only typecheck) passes.
- Start uvicorn, open 跑单管理, confirm `跑单日期` reflects `MIN(mrp_run_time)` per order and is read-only; confirm sort by 跑单日期 works.
- Spot-check an order with no MRP data shows `-` / empty.
