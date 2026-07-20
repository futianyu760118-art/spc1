# ProductionTaskOrder sale_order_id Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a nullable integer foreign key `sale_order_id` (→ `sale_order.id`) to the `production_task_order` table so cross-table joins can use indexed integer keys, without backfilling history or changing OA sync logic.

**Architecture:** Schema-only change. Add column to SQLAlchemy model; register in `init_database.py` `migrate_columns` (first entry for this table); add a follow-up Alembic migration that also installs the FK constraint and the index; expose the new field through the data-supply registry and the external read API.

**Tech Stack:** FastAPI / SQLAlchemy 2.x async / Alembic / PostgreSQL

---

## Global Constraints

- `init_database.py` is the runtime source of truth — any new column must be registered in `migrate_columns[table]` so it appears after container restart (AGENTS.md).
- ERP sync must only overwrite rows where `data_source = 'erp'`; this change does not touch sync, so the guard is preserved by not editing `erp_sync_service.py`.
- `production_task_order` is currently NOT registered in `init_database.py`'s `new_columns` dict — this change is the first entry.
- No pytest/jest in repo (AGENTS.md); verification is by `alembic upgrade head`, `python init_database.py`, uvicorn start, and direct SQL.
- Frontend has no `ProductionTaskOrder` consumer; no TS changes required, but `npm run build` is run for safety.

---

## Task 1: Add `sale_order_id` column and index to model

**Files:**
- Modify: `backend/app/models/production/production_task_order.py`

**Step 1.1: Add `ForeignKey` to the `sqlalchemy` import**

In the existing import line:

```python
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Index, text
```

add `ForeignKey`:

```python
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Index, text
```

**Step 1.2: Add the `sale_order_id` column**

Insert a new line after line 25 (`sale_order_no = ...`):

```python
    sale_order_id = Column(Integer, ForeignKey("sale_order.id"), nullable=True, comment="销售订单ID")
```

**Step 1.3: Add the index in `__table_args__`**

In the `__table_args__` tuple (lines 39-43), append a new `Index(...)` entry:

```python
    __table_args__ = (
        Index("uq_production_task_order_task_id", "task_id", unique=True, postgresql_where=text("task_id IS NOT NULL")),
        Index("ix_production_task_order_task_no", "task_no"),
        Index("ix_production_task_order_material_code", "material_code"),
        Index("ix_production_task_order_sale_order_no", "sale_order_no"),
        Index("ix_production_task_order_sale_order_id", "sale_order_id"),
    )
```

**Step 1.4: Verify file is well-formed**

Run:

```bash
cd backend && python -c "from app.models.production.production_task_order import ProductionTaskOrder; print([c.name for c in ProductionTaskOrder.__table__.columns if c.name == 'sale_order_id'])"
```

Expected output: `['sale_order_id']` (printed as a list with that one entry).

---

## Task 2: Register column in `init_database.py` `migrate_columns`

**Files:**
- Modify: `backend/init_database.py`

**Step 2.1: Add `production_task_order` to the `new_columns` dict**

In the `new_columns` dict inside `migrate_columns()` (around lines 104-273), insert a new key. The alphabetical neighbors in the `p` section are `process_progress` (line 169) and `purchase_order` (line 160). Insert this block between `purchase_order` (ends at line 168) and `process_progress` (starts at line 169):

```python
            "production_task_order": {
                "sale_order_id": "INTEGER",
            },
```

Final position in the file: between the closing brace of `"purchase_order"` and the line `"process_progress": {`. The dict ordering in this file is by table name, so confirm by reading the surrounding lines after editing.

**Step 2.2: Verify the entry parses**

Run:

```bash
cd backend && python -c "import ast; ast.parse(open('init_database.py', encoding='utf-8').read()); print('ok')"
```

Expected output: `ok`.

---

## Task 3: Create Alembic migration

**Files:**
- Create: `backend/alembic/versions/20260715_add_production_task_order_sale_order_id.py`

**Step 3.1: Create the migration file**

Create `backend/alembic/versions/20260715_add_production_task_order_sale_order_id.py` with this exact content:

```python
"""add production_task_order.sale_order_id

Revision ID: 20260715_add_production_task_order_sale_order_id
Revises: add_production_task_order
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_add_production_task_order_sale_order_id"
down_revision: Union[str, None] = "add_production_task_order"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "production_task_order",
        sa.Column("sale_order_id", sa.Integer(), nullable=True, comment="销售订单ID"),
    )
    op.create_index(
        "ix_production_task_order_sale_order_id",
        "production_task_order",
        ["sale_order_id"],
    )
    op.create_foreign_key(
        "fk_production_task_order_sale_order_id",
        "production_task_order",
        "sale_order",
        ["sale_order_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_production_task_order_sale_order_id",
        "production_task_order",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_production_task_order_sale_order_id",
        table_name="production_task_order",
    )
    op.drop_column("production_task_order", "sale_order_id")
```

**Step 3.2: Verify the file parses and is the current head**

Run:

```bash
cd backend && alembic heads
```

Expected output: a single head `20260715_add_production_task_order_sale_order_id (head)`. The current chain is `... rename_scm_material_erp_id → add_production_task_order → 20260715_add_production_task_order_sale_order_id`.

**Step 3.3: Apply the migration**

Run:

```bash
cd backend && alembic upgrade head
```

Expected output: a line containing `20260715_add_production_task_order_sale_order_id` and a success message. No errors.

**Step 3.4: Verify in DB**

Run (using `.env.local` DB):

```bash
psql "$DATABASE_URL" -c "\d production_task_order"
```

Expected: a row `sale_order_id | integer` and an index `ix_production_task_order_sale_order_id` and a foreign-key constraint `fk_production_task_order_sale_order_id`.

If the environment doesn't expose `psql` or the DSN, fall back to:

```bash
cd backend && python -c "
import asyncio
from app.core.database import engine
from sqlalchemy import text
async def m():
    async with engine.begin() as c:
        r = await c.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='production_task_order' AND column_name='sale_order_id'\"))
        print('column:', r.scalar())
        r = await c.execute(text(\"SELECT indexname FROM pg_indexes WHERE tablename='production_task_order' AND indexname='ix_production_task_order_sale_order_id'\"))
        print('index:', r.scalar())
asyncio.run(m())
"
```

Expected output: `column: sale_order_id` and `index: ix_production_task_order_sale_order_id`.

---

## Task 4: Expose new field in data-supply registry

**Files:**
- Modify: `backend/app/services/basicdata/data_supply_registry.py`

**Step 4.1: Add `sale_order_id` to `exposed_fields`**

In the `ProductionTaskOrder` data-type definition (around lines 297-307), update the `exposed_fields` list. Replace:

```python
        "task_type", "sale_order_no",
```

with:

```python
        "task_type", "sale_order_no", "sale_order_id",
```

(Do **not** modify `filter_fields` or `search_fields` — out of scope.)

**Step 4.2: Verify file parses**

Run:

```bash
cd backend && python -c "import ast; ast.parse(open('app/services/basicdata/data_supply_registry.py', encoding='utf-8').read()); print('ok')"
```

Expected: `ok`.

---

## Task 5: Expose new field in external read API

**Files:**
- Modify: `backend/app/api/v1/external/endpoints/production_task_orders.py`

**Step 5.1: Add `sale_order_id` to the items dict**

In the `items` comprehension (lines 119-144), insert a new key right after `"sale_order_no": r.sale_order_no,`:

```python
        "sale_order_no": r.sale_order_no,
        "sale_order_id": r.sale_order_id,
```

(Do **not** add a query parameter; the field is read-only in this endpoint.)

**Step 5.2: Verify file parses**

Run:

```bash
cd backend && python -c "import ast; ast.parse(open('app/api/v1/external/endpoints/production_task_orders.py', encoding='utf-8').read()); print('ok')"
```

Expected: `ok`.

---

## Task 6: End-to-end verification

**Step 6.1: Run `init_database.py` to confirm `migrate_columns` is idempotent**

```bash
cd backend && python init_database.py
```

Expected: log line `Column production_task_order.sale_order_id ...` either says it's already present (skipped) or was added; no exception, no rollback.

**Step 6.2: Start uvicorn and confirm the external endpoint returns the new field**

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

In another terminal, login and call the endpoint:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/basicdata/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "login_type=employee&username=admin&password=admin123" | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/external/production-task-orders/list?page=1&page_size=1" \
  | python -c "import sys,json; d=json.load(sys.stdin); item=d['data']['items'][0] if isinstance(d['data'], dict) else d['data'][0]; print('sale_order_id in item:', 'sale_order_id' in item)"
```

Expected: `sale_order_id in item: True`.

If the project's `data` envelope differs, adjust the JSON path. The key check is that the response payload contains `sale_order_id`.

**Step 6.3: Confirm no sync-side changes**

```bash
cd backend && git diff --stat
```

Expected: modified files limited to the 5 in the spec. `erp_sync_service.py` and `sync_scheduler.py` are **not** in the list.

**Step 6.4: Frontend typecheck (sanity)**

```bash
cd frontend && npm run build
```

Expected: build succeeds. (Frontend does not consume `ProductionTaskOrder`, but this guards against accidental cross-impact.)

**Step 6.5: Commit**

Compose a commit message in the repo style. Suggested:

```
feat(production): add sale_order_id FK to production_task_order

- ProductionTaskOrder.sale_order_id (Integer, FK -> sale_order.id), nullable, indexed
- Registered in init_database.py migrate_columns
- Alembic migration: 20260715_add_production_task_order_sale_order_id
- Exposed via data_supply_registry and external read API
- No backfill, sync logic unchanged
```

(Do **not** commit unless explicitly asked.)

---

## Done Criteria

- All 5 files match the spec.
- `alembic upgrade head` is clean.
- `python init_database.py` is idempotent (running it twice does not error).
- `production_task_order` schema has the new column, the new index, and the FK constraint.
- External API response includes `sale_order_id`.
- Frontend builds.
