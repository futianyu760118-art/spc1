# Design: scm_material `material_id` → `erp_material_id` (int)

**Date:** 2026-07-13
**Status:** Draft, pending user approval
**Scope:** `scm_material.material_id` (rename + type change), `scm_material.parent_id` (type change), plus `scm_bom.material_id` and `scm_bom_detail.material_id` (type change only, to keep joins valid).

---

## 1. Background

`scm_material.material_id` is currently `VARCHAR(50) UNIQUE` and stores ERP-side identifiers. Two problems:

- The column is a self-reference (`parent_id`) **and** a foreign key to `scm_bom.material_id` and `scm_bom_detail.material_id`. Mixed-string joins are slow and error-prone.
- ERP-side identifiers are numeric integers; keeping them as `VARCHAR(50)` forces a cast on every join and prevents index-only scans.

The user has confirmed:
1. The change should extend to `scm_bom` and `scm_bom_detail` (so joins keep working).
2. Existing data in `material_id` is already int-compatible — no special data-migration strategy needed.
3. Both `init_database.py` and a new Alembic migration should be updated.

`scm_bom.parent_material_id` is **not** in scope (it's not joined to `scm_material` anywhere — only returned in responses). It will stay `VARCHAR(50)`.

---

## 2. Schema changes

| Table | Column | Before | After |
|---|---|---|---|
| `scm_material` | `material_id` | `VARCHAR(50) UNIQUE NOT NULL` | **renamed** to `erp_material_id`, type `INTEGER UNIQUE NOT NULL` |
| `scm_material` | `parent_id` | `VARCHAR(50)` | `INTEGER` (self-reference to `erp_material_id`) |
| `scm_bom` | `material_id` | `VARCHAR(50)` | `INTEGER` (references `scm_material.erp_material_id`) |
| `scm_bom_detail` | `material_id` | `VARCHAR(50)` | `INTEGER` (references `scm_material.erp_material_id`) |

**Type-change SQL pattern** (same as the existing `fix_scm_id_columns_to_integer.py` migration for `scm_inventory`):
```sql
ALTER TABLE scm_material ALTER COLUMN material_id TYPE INTEGER USING material_id::integer;
ALTER TABLE scm_material RENAME COLUMN material_id TO erp_material_id;
ALTER TABLE scm_material ALTER COLUMN parent_id TYPE INTEGER USING parent_id::integer;

ALTER TABLE scm_bom ALTER COLUMN material_id TYPE INTEGER USING material_id::integer;
ALTER TABLE scm_bom_detail ALTER COLUMN material_id TYPE INTEGER USING material_id::integer;
```

Order matters: the rename happens **after** the type change on `scm_material`, so the temporary column name during the `USING` cast is the original `material_id`. (The rename itself is a catalog operation that doesn't touch data, so doing it after the cast is safe.)

UNIQUE constraint on `scm_material.erp_material_id` is preserved automatically (PostgreSQL reuses the index underlying the unique constraint when the type changes).

---

## 3. Code changes (backend)

### 3.1 Models

`backend/app/models/basicdata/material.py`:
```python
erp_material_id = Column(Integer, nullable=False, unique=True, comment="ERP物料ID")
parent_id = Column(Integer, nullable=True, comment="父级物料ID(引用erp_material_id)")
```

`backend/app/models/basicdata/bom.py`:
```python
material_id = Column(Integer, nullable=True, comment="物料ID(引用scm_material.erp_material_id)")
# parent_material_id stays VARCHAR(50) — not in scope
```

`backend/app/models/basicdata/bom_detail.py`:
```python
material_id = Column(Integer, nullable=True, comment="物料ID(引用scm_material.erp_material_id)")
```

### 3.2 Pydantic schemas

`backend/app/schemas/basicdata/schemas.py`:
- `MaterialBase.material_id: str` → `erp_material_id: int`
- `MaterialBase.parent_id: Optional[str]` → `Optional[int]`
- `MaterialUpdate`: drop `material_id` from updatable fields (it's the business key, lives in the URL); keep `parent_id: Optional[int] = None`
- `MaterialTreeNode.material_id: str` → `erp_material_id: int`
- `MaterialTreeNode.parent_id: Optional[str]` → `Optional[int]`

### 3.3 API endpoints

`backend/app/api/v1/basicdata/basicdata.py` (7 sites):
- L285: `.order_by(Material.parent_id.nullsfirst(), Material.id)` — keep, `parent_id` column still exists, just now int
- L289: `node_map: dict[str, MaterialTreeNode]` → `dict[int, MaterialTreeNode]`
- L293: `MaterialTreeNode(id=item.id, material_id=item.material_id, parent_id=item.parent_id, ...)` → use `item.erp_material_id`
- L300: `node_map[item.material_id]` → `node_map[item.erp_material_id]`
- L304: `node_map.get(item.parent_id)` — no change to lookup, just keys are int now
- L316: `parent_id: Optional[str] = Query(None, ...)` → `Optional[int]`
- L337–339: no SQL change (filter syntax identical for int), but the value compared is now int
- L360: `@router.get("/materials/{material_id}")` → `"/materials/{erp_material_id}"`, `material_id: str` → `erp_material_id: int`
- L364: `Material.material_id == material_id` → `Material.erp_material_id == erp_material_id`
- L372–386: `create_material` — uniqueness check on `Material.erp_material_id`; create body uses `erp_material_id`
- L389–403: `update_material` — same URL/filter rename
- L406–419: `delete_material` — same URL/filter rename

### 3.4 Other backend files

| File | Change |
|---|---|
| `backend/app/api/v1/external/endpoints/bom.py:65` | `Bom.material_id == Material.material_id` → `Bom.material_id == Material.erp_material_id` |
| `backend/app/api/v1/external/endpoints/bom_detail.py:59,71,72,93` | same `Material.material_id` → `Material.erp_material_id`; the param is now int-typed by the column |
| `backend/app/api/v1/external/endpoints/masterdata.py:310` | `r.material_id` → `r.erp_material_id` in response dict |
| `backend/app/services/order/order_materials_service.py:195,197,217,225` | `Material.material_id` → `Material.erp_material_id`; dict types `dict[str, Material]` → `dict[int, Material]` |
| `backend/app/services/material/kit_analysis_service.py:376,379,384,387` | same rename; type annotations `set[str]` → `set[int]`, `dict[str, ...]` → `dict[int, ...]` |
| `backend/app/services/assistant/tools/search_bom_details.py:106,107,153` | `Material.material_id` → `Material.erp_material_id` |

The `data_supply_registry.py` field lists (`"material_id"` for materials) need an entry update — the exposed field for `Material` should become `"erp_material_id"`. (For Bom and BomDetail, `material_id` is **not** renamed, only the type changes, so the registry strings stay.) Filter/search fields referencing `Material.material_id` need to switch to `Material.erp_material_id` too.

### 3.5 ERP sync

`backend/app/services/basicdata/erp_sync_service.py` material sync uses `_filter_model_fields` and `_coerce_row_types` driven by the SQLAlchemy model + the runtime `field_mapping` table. Once the model field is renamed to `erp_material_id`, the sync will read/write that field automatically. **No code change in this file is required**, but the `field_mapping` row for `materials.material_id` must be updated in the DB to map the SQL column → `erp_material_id` instead of `material_id`. The user owns the `field_mapping` data (it's in `sync_sql_config` / `field_mapping` tables per `backend/ERP_INTEGRATION.md`).

---

## 4. Code changes (frontend)

`frontend/src/pages/BasicDataCenter/Materials.tsx`:
- `Material` interface: `material_id: string` → `erp_material_id: number`, `parent_id?: string | null` → `parent_id?: number | null`
- `TreeNode` interface: `id: string` → `id: number`, etc.
- `buildTreeData`: update `Record<string, TreeNode>` → `Record<number, TreeNode>`, use `erp_material_id` as key
- `filterSelfFromTree`: `excludeId: string` → `excludeId: number`
- `handleDelete(materialId: string)` → `handleDelete(materialId: number)`
- `api.put(\`/basicdata/materials/${editingItem.material_id}\`, values)` → use `editingItem.erp_material_id`
- `api.delete(\`/basicdata/materials/${materialId}\`)` — same
- Form `Form.Item name="material_id"` → `name="erp_material_id"`, label "物料ID" → "ERP物料ID" (or keep label and just rename the field)
- `values.parent_id === editingItem.material_id` — compares int to int now
- Table column `dataIndex: 'material_id'` → `dataIndex: 'erp_material_id'`, title "物料ID" → "ERP物料ID"
- TreeSelect still works with int keys

---

## 5. init_database.py

`backend/init_database.py` lines 188–193 currently ADD `material_id` and `parent_id` to `scm_material`. After the rename, `migrate_columns` is for adding **new** columns only (it uses `ADD COLUMN IF NOT EXISTS`). A rename/type-change must be a separate, idempotent block. I'll add a new method `migrate_scm_material_erp_id()` that:

1. Checks if `scm_material.erp_material_id` exists; if not, performs the `ALTER TYPE INTEGER` then `RENAME COLUMN`.
2. Same for `scm_material.parent_id`.
3. Same for `scm_bom.material_id` and `scm_bom_detail.material_id`.

All wrapped in `async with self.engine.begin() as conn:` and using `try/except` so a partially-migrated DB still works. Called from `init_database.py`'s top-level `init()` (around line 1497) after `migrate_columns()`.

---

## 6. Alembic migration

New file: `backend/alembic/versions/rename_scm_material_id_to_erp_material_id.py`

- `revision = 'rename_scm_material_erp_id'`
- `down_revision = 'merge_heads_20260629'` (current head)
- `upgrade()`:
  - `ALTER TABLE scm_material ALTER COLUMN material_id TYPE INTEGER USING material_id::integer`
  - `ALTER TABLE scm_material RENAME COLUMN material_id TO erp_material_id`
  - `ALTER TABLE scm_material ALTER COLUMN parent_id TYPE INTEGER USING parent_id::integer`
  - `ALTER TABLE scm_bom ALTER COLUMN material_id TYPE INTEGER USING material_id::integer`
  - `ALTER TABLE scm_bom_detail ALTER COLUMN material_id TYPE INTEGER USING material_id::integer`
- `downgrade()`: reverse the above, using `::text` for the type downgrade

---

## 7. Verification plan

1. `cd backend && python -c "from app.models.basicdata.material import Material; print(Material.erp_material_id.type)"` — model imports cleanly
2. `cd frontend && npm run build` — TypeScript compiles (the only "typecheck" per AGENTS.md)
3. Run Alembic: `alembic upgrade head` against a copy of the dev DB, verify column types via `\d scm_material`
4. Run `python init_database.py` against the same DB, verify it's idempotent (run twice, no errors)
5. Hit `GET /api/v1/basicdata/materials/tree` with the seeded admin token — returns a tree, int IDs flow through
6. Hit `GET /api/v1/basicdata/boms/list?material_code=<one>` — join still works
7. Frontend smoke: open Materials page, switch to tree view, add a child material, edit, delete — all without console errors

---

## 8. Risks / not in scope

- `scm_bom.parent_material_id` stays `VARCHAR(50)`. If ERP starts sending int parent IDs, this needs a follow-up.
- `mrp_plan_order.material_id` (composite PK with `sale_order_id`) and `inventory.material_id` (already `INTEGER`) are independent — out of scope.
- ERP `field_mapping` row for materials must be updated to map SQL column `material_id` → model `erp_material_id`. This is runtime DB data, not code.
- If any client passes a non-numeric string into `material_id` filter via query/URL, it will get a 422 (int-typed param) instead of silently returning empty results.
