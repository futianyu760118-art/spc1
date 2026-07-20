# 跑单时间(天) 派生 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make 跑单管理's `跑单时间(天)` (`run_days`) field read-time derived as `(MIN(mrp_plan_order.mrp_run_time).date() − po_placed_date).days`, mirroring the existing 跑单日期 derivation from the 2026-07-13 spec. Negative values allowed; `NULL` when either side is `NULL`.

**Architecture:** Two changes — (1) backend computes `run_days` from `mrp_run_time` (already on the row tuple) and `po_placed_date` (already on the row tuple) in the post-fetch loop and on the detail query; sort column remapped to a SQL `date − date` expression. (2) Frontend 跑单时间(天) cell becomes read-only; create/edit modals' `run_days` input gets `disabled` + tooltip.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2 (asyncpg) on the backend; React + TypeScript + Ant Design 5 on the frontend. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-15-run-order-days-derived-from-mrp-run-time-design.md` (approved).

---

## Global Constraints

- Python 3.12, backend entrypoint `app/main.py`, async SQLAlchemy via `get_db()` in `app/core/database.py` (auto-commit on success, rollback on exception — do **not** commit manually inside the endpoint).
- `init_database.py` is the runtime source of truth for schema — but this change requires **no schema change** (no new column, no `init_database.py` edit, no Alembic).
- Response envelope is mandatory: all endpoints return `{ code, message, data }` (see `ResponseModel` / `PageResult` in `app/schemas/common.py`).
- ERP sync only overwrites `data_source = 'erp'` rows; do not touch the `run_order` row from sync logic (out of scope per spec).
- Frontend path alias `@` → `src/`. `npm run build` (= `tsc -b && vite build`) is the **only** typecheck; run it before declaring done.
- No test suite in this repo — verify by running uvicorn and hitting the endpoint, or by inspection of the changed code.

---

## Task 1: Add the SQL date-delta expression to the list query

**Files:**
- `backend/app/api/v1/order/run_order.py:19-27` (subquery block, no change needed)
- `backend/app/api/v1/order/run_order.py:29-45` (sort mapping, will be edited in Task 3)
- `backend/app/api/v1/order/run_order.py:63-68` (main `select(...)` projection)

**Step 1.1** — Open `backend/app/api/v1/order/run_order.py` and locate the main `select(...)` block at lines 63-68:

```python
query = select(
    SaleOrder,
    RunOrder,
    RunOrder.id.label('run_order_id'),
    case((RunOrder.id.isnot(None), True), else_=False).label('is_synced'),
    _mrp_min_run_time.c.mrp_run_time.label('mrp_run_time'),
).outerjoin(
    RunOrder, SaleOrder.order_no == RunOrder.order_no
).outerjoin(
    _mrp_min_run_time, _mrp_min_run_time.c.order_no == SaleOrder.order_no
)
```

**Step 1.2** — Add a `mrp_run_days` projection directly under `mrp_run_time`:

Replace the `select(...)` block with:

```python
query = select(
    SaleOrder,
    RunOrder,
    RunOrder.id.label('run_order_id'),
    case((RunOrder.id.isnot(None), True), else_=False).label('is_synced'),
    _mrp_min_run_time.c.mrp_run_time.label('mrp_run_time'),
    (func.date(_mrp_min_run_time.c.mrp_run_time) - SaleOrder.order_date).label('mrp_run_days'),
).outerjoin(
    RunOrder, SaleOrder.order_no == RunOrder.order_no
).outerjoin(
    _mrp_min_run_time, _mrp_min_run_time.c.order_no == SaleOrder.order_no
)
```

> **Why this works:** PostgreSQL's `date − date` returns an `integer` (the day delta, positive when the right side is earlier). `func.date(...)` truncates the `DateTime` mrp_run_time to a `Date` so the operand types match. `func` is already imported on line 4.

**Step 1.3** — Verify by reading the file. The projection now has 6 entries; the joins are unchanged.

---

## Task 2: Compute `run_days` in the list row loop and override on every item

**Files:**
- `backend/app/api/v1/order/run_order.py:132-170` (the `for row in result.all():` loop)

**Step 2.1** — Locate the loop body. The current state:

```python
items = []
for row in result.all():
    sale_order = row[0]
    run_order = row[1]
    is_synced = row.is_synced
    mrp_run_time = row.mrp_run_time
    run_date_val = mrp_run_time.date() if mrp_run_time else None
    if run_order:
        item = RunOrderOut.model_validate(run_order)
        item.is_synced = True
        item.run_date = run_date_val
    else:
        # 从 sale_order 映射到 RunOrderOut
        item = RunOrderOut(
            id=None,
            customer_code=sale_order.customer_code,
            order_no=sale_order.order_no,
            order_qty=float(sale_order.order_qty) if sale_order.order_qty else None,
            order_type=sale_order.order_nature,
            contract_date=sale_order.order_date,
            delivery_date=sale_order.promised_date,
            run_date=run_date_val,
            run_days=None,
            order_amount=None,
            packaging_not_released=None,
            po_placed_date=sale_order.order_date,
            material_ready_date=sale_order.material_ready_date,
            procurement_cycle=None,
            completed_date=None,
            shipped_date=None,
            order_status=None,
            delay_reason=None,
            remark=sale_order.remark,
            is_domestic=False,
            is_synced=is_synced,
            created_at=sale_order.created_at,
            updated_at=sale_order.updated_at,
        )
    items.append(item)
```

**Step 2.2** — Compute `run_days_val` next to `run_date_val`, then set it on the item in **both** branches (synced and un-synced). The existing `run_days=None` literal in the un-synced branch stays where it is — we override it after the branch.

Replace the entire `for row in result.all():` block with:

```python
items = []
for row in result.all():
    sale_order = row[0]
    run_order = row[1]
    is_synced = row.is_synced
    mrp_run_time = row.mrp_run_time
    po_placed_date = sale_order.order_date
    run_date_val = mrp_run_time.date() if mrp_run_time else None
    run_days_val = (
        (mrp_run_time.date() - po_placed_date).days
        if (mrp_run_time and po_placed_date) else None
    )
    if run_order:
        item = RunOrderOut.model_validate(run_order)
        item.is_synced = True
        item.run_date = run_date_val
        item.run_days = run_days_val
    else:
        # 从 sale_order 映射到 RunOrderOut
        item = RunOrderOut(
            id=None,
            customer_code=sale_order.customer_code,
            order_no=sale_order.order_no,
            order_qty=float(sale_order.order_qty) if sale_order.order_qty else None,
            order_type=sale_order.order_nature,
            contract_date=sale_order.order_date,
            delivery_date=sale_order.promised_date,
            run_date=run_date_val,
            run_days=run_days_val,
            order_amount=None,
            packaging_not_released=None,
            po_placed_date=sale_order.order_date,
            material_ready_date=sale_order.material_ready_date,
            procurement_cycle=None,
            completed_date=None,
            shipped_date=None,
            order_status=None,
            delay_reason=None,
            remark=sale_order.remark,
            is_domestic=False,
            is_synced=is_synced,
            created_at=sale_order.created_at,
            updated_at=sale_order.updated_at,
        )
    items.append(item)
```

**Step 2.3** — Verify by reading lines 130-180. Both branches now compute `run_days_val` from `(mrp_run_time.date() − po_placed_date).days` and the `item.run_days` is overridden in both.

---

## Task 3: Repoint the `run_days` sort mapping to the SQL delta expression

**Files:**
- `backend/app/api/v1/order/run_order.py:29-45` (`RUN_ORDER_SORTABLE_COLUMNS` dict)

**Step 3.1** — Replace the entry for `'run_days'` (currently line 37: `'run_days': RunOrder.run_days,`).

The new value is a SQL expression identical to the one added in Task 1. To keep them in sync, build a module-level alias **once** above the dict, then reference it from both the select and the sort mapping.

Insert directly above `RUN_ORDER_SORTABLE_COLUMNS` (i.e. after the `_mrp_min_run_time` subquery block, around line 27):

```python
_mrp_min_run_time_days = (
    (func.date(_mrp_min_run_time.c.mrp_run_time) - SaleOrder.order_date)
    .label("mrp_run_days")
)
```

Then in the dict, change line 37 from:

```python
    'run_days': RunOrder.run_days,
```

to:

```python
    'run_days': _mrp_min_run_time_days,
```

**Step 3.2** — Now refactor the main `select(...)` (the one you edited in Task 1) so the projection references the **same** alias (avoids drift if the expression ever changes):

```python
query = select(
    SaleOrder,
    RunOrder,
    RunOrder.id.label('run_order_id'),
    case((RunOrder.id.isnot(None), True), else_=False).label('is_synced'),
    _mrp_min_run_time.c.mrp_run_time.label('mrp_run_time'),
    _mrp_min_run_time_days.label('mrp_run_days'),
).outerjoin(
    RunOrder, SaleOrder.order_no == RunOrder.order_no
).outerjoin(
    _mrp_min_run_time, _mrp_min_run_time.c.order_no == SaleOrder.order_no
)
```

> **Note:** SQLAlchemy `.label('mrp_run_days')` chained from the `date − date` expression produces the same column reference whether used in `select(...)` or in `order_by(...)`. The `.label('mrp_run_days')` on the module-level alias is the source of truth; the inline `.label(...)` in the `select(...)` is redundant but harmless. We keep it for readability.

**Step 3.3** — Verify by reading lines 19-50. The new `_mrp_min_run_time_days` alias appears once at module level and is used in both the `select(...)` projection and the `'run_days'` sort entry.

---

## Task 4: Compute `run_days` in the detail endpoint

**Files:**
- `backend/app/api/v1/order/run_order.py:183-201` (`get_run_order`)

**Step 4.1** — Replace the `get_run_order` function body so it selects `SaleOrder.order_date` alongside `mrp_run_time` and sets `out.run_days`.

Current code (lines 183-201):

```python
@router.get("/{run_order_id}", response_model=ResponseModel[RunOrderOut])
async def get_run_order(
    run_order_id: int,
    current_user: dict = Depends(PermissionChecker("orders.run_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RunOrder, _mrp_min_run_time.c.mrp_run_time.label('mrp_run_time'))
        .outerjoin(_mrp_min_run_time, _mrp_min_run_time.c.order_no == RunOrder.order_no)
        .where(RunOrder.id == run_order_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="跑单记录不存在")
    run_order = row[0]
    mrp_run_time = row.mrp_run_time
    out = RunOrderOut.model_validate(run_order)
    out.run_date = mrp_run_time.date() if mrp_run_time else None
    return ResponseModel(data=out)
```

Replace with:

```python
@router.get("/{run_order_id}", response_model=ResponseModel[RunOrderOut])
async def get_run_order(
    run_order_id: int,
    current_user: dict = Depends(PermissionChecker("orders.run_orders", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            RunOrder,
            _mrp_min_run_time.c.mrp_run_time.label('mrp_run_time'),
            SaleOrder.order_date.label('po_placed_date'),
        )
        .outerjoin(SaleOrder, SaleOrder.order_no == RunOrder.order_no)
        .outerjoin(_mrp_min_run_time, _mrp_min_run_time.c.order_no == RunOrder.order_no)
        .where(RunOrder.id == run_order_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="跑单记录不存在")
    run_order = row[0]
    mrp_run_time = row.mrp_run_time
    po_placed_date = row.po_placed_date
    out = RunOrderOut.model_validate(run_order)
    out.run_date = mrp_run_time.date() if mrp_run_time else None
    out.run_days = (
        (mrp_run_time.date() - po_placed_date).days
        if (mrp_run_time and po_placed_date) else None
    )
    return ResponseModel(data=out)
```

> **Why the extra join on `SaleOrder`:** the existing query only joined `_mrp_min_run_time`; we need `po_placed_date` from `SaleOrder.order_date`. `SaleOrder` is already imported (line 12).

**Step 4.2** — Verify by reading lines 183-205. The detail endpoint now joins `SaleOrder`, selects `po_placed_date`, and computes `out.run_days` mirroring the list loop.

---

## Task 5: Make the 跑单时间(天) cell read-only

**Files:**
- `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx:404-407`

**Step 5.1** — Locate the column definition:

```tsx
{
  title: '跑单时间(天)', dataIndex: 'run_days', key: 'run_days', width: 95, align: 'right' as const, sorter: true,
  render: editableNumber('run_days'),
},
```

**Step 5.2** — Replace with a read-only render that matches the 跑单日期 cell's pattern (line 401-403 above it):

```tsx
{
  title: '跑单时间(天)', dataIndex: 'run_days', key: 'run_days', width: 95, align: 'right' as const, sorter: true,
  render: (v: number | null | undefined) => (v === null || v === undefined ? <span style={{ color: '#cbd5e1' }}>-</span> : v),
},
```

> **Why this works:** the stored `run_order.run_days` is no longer used for display. The cell now shows the backend-computed value (a plain integer) and renders `-` for NULL.

**Step 5.3** — Verify by reading lines 401-410. Both 跑单日期 and 跑单时间(天) cells now use the read-only `render: (v) => v ?? '-'` style.

---

## Task 6: Disable `run_days` in the create modal

**Files:**
- `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx:593-597`

**Step 6.1** — Locate the create modal's `run_days` Form.Item:

```tsx
<Col span={12}>
  <Form.Item name="run_days" label="跑单时间(天)">
    <InputNumber min={0} style={{ width: '100%' }} placeholder="选填" />
  </Form.Item>
</Col>
```

**Step 6.2** — Add `disabled` to the `InputNumber` and a `tooltip` to the `Form.Item` (mirror the 跑单日期 Form.Item directly above it on line 589):

```tsx
<Col span={12}>
  <Form.Item name="run_days" label="跑单时间(天)" tooltip="自动计算自 MRP 运算时间 − 下单时间">
    <InputNumber min={0} style={{ width: '100%' }} placeholder="选填" disabled />
  </Form.Item>
</Col>
```

**Step 6.3** — Verify by reading lines 588-598. The create modal's `run_days` now matches the `run_date` item's disabled/tooltip style.

---

## Task 7: Disable `run_days` in the edit modal

**Files:**
- `frontend/src/pages/OrderDelivery/RunOrderList/index.tsx:712-716`

**Step 7.1** — Locate the edit modal's `run_days` Form.Item:

```tsx
<Col span={12}>
  <Form.Item name="run_days" label="跑单时间(天)">
    <InputNumber min={0} style={{ width: '100%' }} />
  </Form.Item>
</Col>
```

**Step 7.2** — Add `disabled` to the `InputNumber` and a `tooltip` to the `Form.Item` (mirror the 跑单日期 Form.Item directly above it on line 708):

```tsx
<Col span={12}>
  <Form.Item name="run_days" label="跑单时间(天)" tooltip="自动计算自 MRP 运算时间 − 下单时间">
    <InputNumber min={0} style={{ width: '100%' }} disabled />
  </Form.Item>
</Col>
```

**Step 7.3** — Verify by reading lines 707-717. The edit modal's `run_days` now matches the `run_date` item's disabled/tooltip style.

---

## Task 8: Frontend typecheck

**Files:** none (verification).

**Step 8.1** — Run the build from the frontend directory:

```bash
cd frontend
npm run build
```

**Step 8.2** — Confirm `tsc -b` and `vite build` exit 0. The output should end with something like `✓ built in N.NNs` and no TypeScript errors. If `tsc` reports an error, the most likely culprit is the new `(v: number | null | undefined) => ...` render — verify the type annotation matches `RunOrderOut.run_days` (declared in `frontend/src/services/api.ts` via the backend's `RunOrderOut` schema; should be `Optional[int]`).

---

## Task 9: Backend smoke test (manual)

**Files:** none (verification — start uvicorn, hit the endpoint).

**Step 9.1** — Start the backend (per AGENTS.md):

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Step 9.2** — Log in (per AGENTS.md: form-urlencoded, `login_type=employee`):

```bash
curl -s -X POST http://localhost:8000/api/v1/basicdata/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "login_type=employee&username=admin&password=admin123" | jq .
```

Capture the `access_token` from the response.

**Step 9.3** — Call the list endpoint:

```bash
curl -s "http://localhost:8000/api/v1/run-orders?page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN" | jq '.data.items[] | {order_no, run_date, run_days, po_placed_date}'
```

**Step 9.4** — Verify the output:

- For each row, `run_days === (run_date − po_placed_date)` in days (or `null` if either is `null`).
- Negative values appear when `run_date < po_placed_date` (MRP re-run case).
- No row shows a stale stored value that disagrees with the formula (sanity-check: pick a row with a `run_days` value that does NOT match `(run_date − po_placed_date)` — there should be none).

**Step 9.5** — Call the detail endpoint on one row:

```bash
curl -s "http://localhost:8000/api/v1/run-orders/$RUN_ORDER_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.data | {order_no, run_date, run_days, po_placed_date}'
```

**Step 9.6** — Verify `run_days` matches the formula. If `RunOrderOut.run_days` is the *stored* value here (because `model_validate` runs first and we only override `run_date`), the test will fail — re-read Task 4 to make sure you replaced the entire `get_run_order` function body and the override line is **after** `model_validate`.

**Step 9.7** — Test the sort:

```bash
curl -s "http://localhost:8000/api/v1/run-orders?page=1&page_size=20&sort_by=run_days&sort_order=asc" \
  -H "Authorization: Bearer $TOKEN" | jq '.data.items[].run_days'
```

Verify the values are non-decreasing (allowing `null`s, which sort to the end per `nullslast()`).

---

## Task 10: Frontend smoke test (manual)

**Files:** none (verification — open the browser).

**Step 10.1** — Start the frontend dev server (per AGENTS.md):

```bash
cd frontend
npm run dev
```

**Step 10.2** — Open `http://localhost:3000/run-orders`, log in as `admin`.

**Step 10.3** — Confirm:

- 跑单时间(天) column shows integer values (e.g. `5`, `-2`) or `-` for `NULL`. No edit pencil on click.
- 跑单日期 column still shows the derived date (no regression from the 2026-07-13 spec).
- Click any row → click the edit button → the modal's 跑单时间(天) input is grayed out with a tooltip "自动计算自 MRP 运算时间 − 下单时间".
- Click "新建跑单" → the create modal's 跑单时间(天) input is grayed out with the same tooltip.
- Sort by 跑单时间(天) asc/desc — order matches the displayed integers (allowing nulls at the end).

---

## Out of scope (do NOT touch)

- `RunOrder.run_days` storage column — kept as-is, just no longer read for display.
- `RunOrderCreate.run_days` / `RunOrderUpdate.run_days` Pydantic schemas — kept as-is to avoid form-binding churn.
- CSV import at `backend/app/services/order/import_csv.py:226, 250, 272` — still writes to `run_order.run_days` (no-op for display).
- `app/services/assistant/tools/search_run_orders.py` — still reads stored `RunOrder.run_days` (follow-up spec if needed).
- `init_database.py` / Alembic — no schema change required.

---

## Commit cadence

- **Commit 1** (after Tasks 1-4): `feat(orders): derive run_days from mrp_run_time − po_placed_date at read time`
- **Commit 2** (after Tasks 5-7): `feat(orders): make run_days cell read-only with auto-calc hint`
- **Commit 3** (after Task 8 + 9 + 10): `chore(orders): verify run_days derivation end-to-end`

(Each commit is a logical, revertable unit. Per AGENTS.md, do not auto-commit — present the diff and let the user commit.)
