# scm_material `material_id` → `erp_material_id` (int) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename `scm_material.material_id` (VARCHAR) to `erp_material_id` (INTEGER UNIQUE), change `scm_material.parent_id` to INTEGER, and change `scm_bom.material_id` + `scm_bom_detail.material_id` to INTEGER so the cross-table joins keep working.

**Architecture:** Rename happens at the DB level (ALTER TYPE → RENAME COLUMN), idempotent in both `init_database.py` and a new Alembic migration. Models, schemas, API endpoints, services, and the frontend `Materials.tsx` are updated to use the new attribute name and int type. ERP sync needs no code change (uses runtime field_mapping).

**Tech Stack:** FastAPI + SQLAlchemy 2.x async + asyncpg, Pydantic v2, Alembic, React + TypeScript + Antd.

## Global Constraints

- TypeScript strict mode. `npm run build` (tsc -b && vite build) is the only typecheck; no lint/test/format scripts exist.
- App code uses async SQLAlchemy via `get_db()` which auto-commits/rolls-back — don't commit manually inside endpoints.
- Response envelope `{code, message, data}` is mandatory on all backend responses.
- DB migration rule: register schema changes in BOTH `init_database.py` AND a new Alembic revision. `init_database.py` is the runtime source of truth (runs on every container start).
- `init_database.py` migration must be idempotent (guard with column-existence check, run inside `try/except`).
- No comments added to code unless asked.
- Backend: Python 3.12; Frontend: Node 20.

---

## Task 1: Update `scm_material` SQLAlchemy model

**Files:**
- `backend/app/models/basicdata/material.py`

**Step 1:** Replace the `material_id` and `parent_id` columns with `erp_material_id` (int) and `parent_id` (int).

Open the file and replace lines 13–14:

```python
material_id = Column(String(50), nullable=False, unique=True, comment="物料ID(外部系统)")
parent_id = Column(String(50), nullable=True, comment="父级物料ID(引用material_id)")
```

with:

```python
erp_material_id = Column(Integer, nullable=False, unique=True, comment="ERP物料ID")
parent_id = Column(Integer, nullable=True, comment="父级物料ID(引用erp_material_id)")
```

`String` is no longer imported for this file. Keep the existing `from sqlalchemy import Column, BigInteger, Integer, DateTime` import (drop `String` if not used elsewhere — it's not used after this change).

**Step 2:** Verify the model still imports.

```bash
cd backend && python -c "from app.models.basicdata.material import Material; print(Material.erp_material_id.type, Material.parent_id.type)"
```

Expected output (exact):
```
Integer Integer
```

---

## Task 2: Update `scm_bom` and `scm_bom_detail` models

**Files:**
- `backend/app/models/basicdata/bom.py`
- `backend/app/models/basicdata/bom_detail.py`

**Step 1:** In `bom.py`, replace line 15:

```python
material_id = Column(String(50), nullable=True, comment="物料ID")
```

with:

```python
material_id = Column(Integer, nullable=True, comment="物料ID(引用scm_material.erp_material_id)")
```

Leave `parent_material_id` (line 16) as `String(50)` — not in scope.

**Step 2:** In `bom_detail.py`, replace line 18:

```python
material_id = Column(String(50), nullable=True, comment="物料ID")
```

with:

```python
material_id = Column(Integer, nullable=True, comment="物料ID(引用scm_material.erp_material_id)")
```

**Step 3:** Verify.

```bash
cd backend && python -c "from app.models.basicdata.bom import Bom; from app.models.basicdata.bom_detail import BomDetail; print(Bom.material_id.type, BomDetail.material_id.type)"
```

Expected output:
```
Integer Integer
```

---

## Task 3: Update Pydantic schemas

**File:** `backend/app/schemas/basicdata/schemas.py`

**Step 1:** Replace `MaterialBase` (lines 127–141) with:

```python
class MaterialBase(BaseModel):
    erp_material_id: int
    parent_id: Optional[int] = None
    material_code: str
    material_name: str
    spec_model: Optional[str] = None
    material_type: str
    unit_of_measure: str
    brand: Optional[str] = None
    is_purchase: int = 0
    is_produce: int = 0
    status: int = 1
    erp_sync_flag: int = 0
    is_deleted: int = 0
```

**Step 2:** Replace `MaterialUpdate` (lines 147–159) with:

```python
class MaterialUpdate(BaseModel):
    parent_id: Optional[int] = None
    material_name: Optional[str] = None
    spec_model: Optional[str] = None
    material_type: Optional[str] = None
    unit_of_measure: Optional[str] = None
    brand: Optional[str] = None
    is_purchase: Optional[int] = None
    is_produce: Optional[int] = None
    status: Optional[int] = None
    erp_sync_flag: Optional[int] = None
    is_deleted: Optional[int] = None
```

`erp_material_id` is not in `MaterialUpdate` — the URL parameter is the business key and shouldn't be changed in-place.

**Step 3:** Replace `MaterialTreeNode` (lines 168–183) with:

```python
class MaterialTreeNode(BaseModel):
    id: int
    erp_material_id: int
    parent_id: Optional[int] = None
    material_code: str
    material_name: str
    spec_model: Optional[str] = None
    material_type: str
    unit_of_measure: str
    brand: Optional[str] = None
    is_purchase: int = 0
    is_produce: int = 0
    status: int = 1
    children: List["MaterialTreeNode"] = []

    model_config = {"from_attributes": True}
```

`MaterialOut(MaterialBase)` stays as-is (it inherits the new `erp_material_id` field).

**Step 4:** Verify.

```bash
cd backend && python -c "from app.schemas.basicdata.schemas import MaterialBase, MaterialUpdate, MaterialTreeNode, MaterialOut; print('OK')"
```

Expected output:
```
OK
```

---

## Task 4: Update basicdata API endpoints

**File:** `backend/app/api/v1/basicdata/basicdata.py`

**Step 1:** Update `get_material_tree` (lines 279–309). Change:

```python
    node_map: dict[str, MaterialTreeNode] = {}
    roots: List[MaterialTreeNode] = []
    for item in all_items:
        node = MaterialTreeNode(
            id=item.id, material_id=item.material_id, parent_id=item.parent_id,
            ...
        )
        node_map[item.material_id] = node
```

to:

```python
    node_map: dict[int, MaterialTreeNode] = {}
    roots: List[MaterialTreeNode] = []
    for item in all_items:
        node = MaterialTreeNode(
            id=item.id, erp_material_id=item.erp_material_id, parent_id=item.parent_id,
            ...
        )
        node_map[item.erp_material_id] = node
```

**Step 2:** Update `list_materials` signature (line 316):

```python
    parent_id: Optional[str] = Query(None, description="父级物料ID筛选, 'root'表示根级"),
```

to:

```python
    parent_id: Optional[int] = Query(None, description="父级物料ID筛选, None表示根级"),
```

The filter logic at lines 337–339 stays the same (NULL check vs equality — the SQL is identical for int).

**Step 3:** Update `get_material` (lines 360–369):

```python
@router.get("/materials/{erp_material_id}", response_model=MaterialOut)
async def get_material(erp_material_id: int, db: AsyncSession = Depends(get_db)):
    """查询单个物料"""
    result = await db.execute(
        select(Material).filter(Material.erp_material_id == erp_material_id, Material.is_deleted == 0)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="物料不存在")
    return item
```

**Step 4:** Update `create_material` (lines 372–386). Replace:

```python
@router.post("/materials", response_model=MaterialOut)
async def create_material(material: MaterialCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建物料"""
    result = await db.execute(select(Material).filter(Material.material_id == material.material_id))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="物料ID已存在")
    
    db_item = Material(**material.model_dump())
    await db.flush()
    await log_audit(db, "material", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item
```

with:

```python
@router.post("/materials", response_model=MaterialOut)
async def create_material(material: MaterialCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "create"))):
    """创建物料"""
    result = await db.execute(select(Material).filter(Material.erp_material_id == material.erp_material_id))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="ERP物料ID已存在")

    db_item = Material(**material.model_dump())
    await db.flush()
    await log_audit(db, "material", db_item.id, "create", operator=current_user["username"])
    await db.commit()
    await db.refresh(db_item)
    return db_item
```

**Step 5:** Update `update_material` (lines 389–403):

```python
@router.put("/materials/{erp_material_id}", response_model=MaterialOut)
async def update_material(erp_material_id: int, material: MaterialUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "update"))):
    """更新物料"""
    result = await db.execute(select(Material).filter(Material.erp_material_id == erp_material_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="物料不存在")

    update_data = material.model_dump(exclude_unset=True)
    await log_audit(db, "material", db_item.id, "update", old_obj=db_item, update_data=update_data, operator=current_user["username"])
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item
```

**Step 6:** Update `delete_material` (lines 406–419):

```python
@router.delete("/materials/{erp_material_id}")
async def delete_material(erp_material_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(PermissionChecker("basicdata.data", "delete"))):
    """逻辑删除物料"""
    result = await db.execute(
        select(Material).filter(Material.erp_material_id == erp_material_id, Material.is_deleted == 0)
    )
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="物料不存在")

    await log_audit(db, "material", db_item.id, "delete", operator=current_user["username"])
    db_item.is_deleted = 1
    await db.commit()
    return {"message": "删除成功"}
```

**Step 7:** Verify file compiles (search for any leftover `Material.material_id`).

```bash
cd backend && grep -n "Material\.material_id" app/api/v1/basicdata/basicdata.py
```

Expected output: empty (no matches).

---

## Task 5: Update external endpoints

**Files:**
- `backend/app/api/v1/external/endpoints/bom.py`
- `backend/app/api/v1/external/endpoints/bom_detail.py`
- `backend/app/api/v1/external/endpoints/masterdata.py`

**Step 1:** In `bom.py` line 65, change:

```python
        query = query.join(Material, Bom.material_id == Material.material_id)
```

to:

```python
        query = query.join(Material, Bom.material_id == Material.erp_material_id)
```

**Step 2:** In `bom_detail.py` line 59, change:

```python
        Material, BomDetail.material_id == Material.material_id
```

to:

```python
        Material, BomDetail.material_id == Material.erp_material_id
```

**Step 3:** In `masterdata.py` line 310, change:

```python
        "material_id": r.material_id,
```

to:

```python
        "erp_material_id": r.erp_material_id,
```

(The response key changes from `material_id` to `erp_material_id` to match the new field name; this is a breaking change to the external API consumers, but the user owns that contract.)

**Step 4:** Verify no leftover `Material.material_id` in external endpoints.

```bash
cd backend && grep -rn "Material\.material_id" app/api/v1/external/endpoints/
```

Expected output: empty.

---

## Task 6: Update internal services

**Files:**
- `backend/app/services/order/order_materials_service.py`
- `backend/app/services/material/kit_analysis_service.py`
- `backend/app/services/assistant/tools/search_bom_details.py`

**Step 1:** In `order_materials_service.py`, change:
- L193: `master_by_mid: dict[str, Material] = {}` → `master_by_mid: dict[int, Material] = {}`
- L195: `Material.material_id.in_(bom_detail_material_ids)` → `Material.erp_material_id.in_(bom_detail_material_ids)`
- L197: `master_by_mid[m.material_id] = m` → `master_by_mid[m.erp_material_id] = m`
- L217: `master_by_mid.get(detail.material_id)` — keep (lookup is on the dict, key is int now)
- L225: `material_id=detail.material_id,` — keep (this is the BomDetail material_id, which stays as the field name and is now int)

**Step 2:** In `kit_analysis_service.py`, change:
- L363: `child_material_ids: set[str] = set()` → `child_material_ids: set[int] = set()`
- L362: `bom_detail_map: dict[str, list[tuple[str, Decimal]]] = {}` → `bom_detail_map: dict[str, list[tuple[int, Decimal]]] = {}`
- L366: `bom_detail_map.setdefault(d.bom_id, []).append((d.material_id, d.standard_qty))` — keep (tuple element is int now, d.material_id is BomDetail.material_id which is now int)
- L376: `Material.material_id.in_(new_material_ids)` → `Material.erp_material_id.in_(new_material_ids)`
- L379: `material_map[m.material_id] = m` → `material_map[m.erp_material_id] = m`
- L382: `sub_material_boms: dict[str, Bom] = {}` → `sub_material_boms: dict[int, Bom] = {}`
- L384: `Bom.material_id.in_(child_material_ids)` — keep (Bom.material_id is the int column, child_material_ids is set[int])
- L387: `sub_material_boms[b.material_id] = b` — keep (key is int)
- L390: `next_queue: list[tuple[str, Decimal, tuple[str, str]]] = []` — keep (this contains bom_id which is String)
- L394: `for material_id, standard_qty in bom_detail_map[bom_id]:` — keep
- L395: `master = material_map.get(material_id)` — keep
- L405: `sub_bom = sub_material_boms.get(material_id)` — keep

**Step 3:** In `search_bom_details.py`, change:
- L106: `select(Bom).where(Bom.material_id == master.material_id)` → `select(Bom).where(Bom.material_id == master.erp_material_id)`
- L107: `select(func.count()).select_from(Bom).where(Bom.material_id == master.material_id)` → `select(func.count()).select_from(Bom).where(Bom.material_id == master.erp_material_id)`
- L153: `.outerjoin(Material, BomDetail.material_id == Material.material_id)` → `.outerjoin(Material, BomDetail.material_id == Material.erp_material_id)`

**Step 4:** Verify no leftover `Material.material_id` in services.

```bash
cd backend && grep -rn "Material\.material_id" app/services/
```

Expected output: empty.

---

## Task 7: Update data_supply_registry

**File:** `backend/app/services/basicdata/data_supply_registry.py`

**Step 1:** In the `materials` registration (line 91), change:

```python
        "id", "material_id", "material_code", "material_name", "spec_model",
```

to:

```python
        "id", "erp_material_id", "material_code", "material_name", "spec_model",
```

Leave the `boms` and `bom_details` registrations unchanged — their `material_id` column is not renamed, only the type changes (still exposed as `material_id`).

**Step 2:** Verify.

```bash
cd backend && python -c "from app.services.basicdata.data_supply_registry import _DATA_TYPES; print([d.exposed_fields[:3] for d in _DATA_TYPES.values() if d.model_name=='Material'])"
```

Expected output:
```
[['id', 'erp_material_id', 'material_code']]
```

---

## Task 8: Add DB migration to init_database.py

**File:** `backend/init_database.py`

**Step 1:** Add a new method to `DatabaseInitializer` class. Place it right after `migrate_columns` (after line 303). Add:

```python
    async def migrate_scm_material_erp_id(self):
        """将 scm_material.material_id 改名为 erp_material_id (INTEGER),
        并把 parent_id / scm_bom.material_id / scm_bom_detail.material_id 改为 INTEGER.
        幂等: 通过 information_schema 检查列是否已是目标类型/名称。"""
        print("Migrating scm_material to erp_material_id (int)...")
        async with self.engine.begin() as conn:
            # 1. scm_material.material_id: type -> integer, rename -> erp_material_id
            exists = (await conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='scm_material' AND column_name='erp_material_id'"
            ))).scalar()
            if not exists:
                try:
                    await conn.execute(text(
                        "ALTER TABLE scm_material ALTER COLUMN material_id "
                        "TYPE INTEGER USING material_id::integer"
                    ))
                    await conn.execute(text(
                        "ALTER TABLE scm_material RENAME COLUMN material_id TO erp_material_id"
                    ))
                    print("  scm_material: material_id -> erp_material_id (int)")
                except Exception as e:
                    print(f"  scm_material rename/type skipped: {e}")
            else:
                print("  scm_material.erp_material_id already exists, skip rename")

            # 2. scm_material.parent_id -> integer
            try:
                await conn.execute(text(
                    "ALTER TABLE scm_material ALTER COLUMN parent_id "
                    "TYPE INTEGER USING parent_id::integer"
                ))
                print("  scm_material.parent_id -> integer")
            except Exception as e:
                print(f"  scm_material.parent_id type change skipped: {e}")

            # 3. scm_bom.material_id -> integer
            try:
                await conn.execute(text(
                    "ALTER TABLE scm_bom ALTER COLUMN material_id "
                    "TYPE INTEGER USING material_id::integer"
                ))
                print("  scm_bom.material_id -> integer")
            except Exception as e:
                print(f"  scm_bom.material_id type change skipped: {e}")

            # 4. scm_bom_detail.material_id -> integer
            try:
                await conn.execute(text(
                    "ALTER TABLE scm_bom_detail ALTER COLUMN material_id "
                    "TYPE INTEGER USING material_id::integer"
                ))
                print("  scm_bom_detail.material_id -> integer")
            except Exception as e:
                print(f"  scm_bom_detail.material_id type change skipped: {e}")

        print("scm_material erp_material_id migration done")
```

**Step 2:** Wire it into `initialize_all`. After line 1497 (`await self.migrate_columns()`), add:

```python
            await self.migrate_scm_material_erp_id()
```

**Step 3:** Verify.

```bash
cd backend && python -c "import ast; ast.parse(open('init_database.py').read()); print('OK')"
```

Expected output:
```
OK
```

---

## Task 9: Add Alembic migration

**File:** `backend/alembic/versions/rename_scm_material_erp_id.py` (new)

**Step 1:** Create the file with the following content:

```python
"""rename scm_material.material_id to erp_material_id (int)

Revision ID: rename_scm_material_erp_id
Revises: merge_heads_20260629
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'rename_scm_material_erp_id'
down_revision: Union[str, None] = 'merge_heads_20260629'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scm_material ALTER COLUMN material_id "
        "TYPE INTEGER USING material_id::integer"
    )
    op.execute(
        "ALTER TABLE scm_material RENAME COLUMN material_id TO erp_material_id"
    )
    op.execute(
        "ALTER TABLE scm_material ALTER COLUMN parent_id "
        "TYPE INTEGER USING parent_id::integer"
    )
    op.execute(
        "ALTER TABLE scm_bom ALTER COLUMN material_id "
        "TYPE INTEGER USING material_id::integer"
    )
    op.execute(
        "ALTER TABLE scm_bom_detail ALTER COLUMN material_id "
        "TYPE INTEGER USING material_id::integer"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE scm_material RENAME COLUMN erp_material_id TO material_id"
    )
    op.execute(
        "ALTER TABLE scm_material ALTER COLUMN material_id "
        "TYPE VARCHAR(50) USING material_id::text"
    )
    op.execute(
        "ALTER TABLE scm_material ALTER COLUMN parent_id "
        "TYPE VARCHAR(50) USING parent_id::text"
    )
    op.execute(
        "ALTER TABLE scm_bom ALTER COLUMN material_id "
        "TYPE VARCHAR(50) USING material_id::text"
    )
    op.execute(
        "ALTER TABLE scm_bom_detail ALTER COLUMN material_id "
        "TYPE VARCHAR(50) USING material_id::text"
    )
```

**Step 2:** Verify the file parses.

```bash
cd backend && python -c "import ast; ast.parse(open('alembic/versions/rename_scm_material_erp_id.py').read()); print('OK')"
```

Expected output:
```
OK
```

---

## Task 10: Update frontend Materials page

**File:** `frontend/src/pages/BasicDataCenter/Materials.tsx`

**Step 1:** Update the `Material` interface (lines 12–28). Replace with:

```typescript
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
  children?: Material[]
}
```

**Step 2:** Update the `TreeNode` interface (lines 30–36). Replace with:

```typescript
interface TreeNode {
  id: number
  value: number
  title: string
  key: number
  children?: TreeNode[]
}
```

**Step 3:** Update `buildTreeData` (lines 38–52). Replace with:

```typescript
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
```

**Step 4:** Update `filterSelfFromTree` signature (line 66):

```typescript
const filterSelfFromTree = (nodes: TreeNode[], excludeId: number): TreeNode[] => {
```

**Step 5:** Update the form (lines 80–136). In the `MaterialForm`, change:

```tsx
    <Form.Item name="material_id" label="物料ID" rules={[{ required: true }]}>
      <Input placeholder="请输入物料ID(外部系统)" />
    </Form.Item>
```

to:

```tsx
    <Form.Item name="erp_material_id" label="ERP物料ID" rules={[{ required: true }]}>
      <InputNumber placeholder="请输入ERP物料ID" style={{ width: '100%' }} />
    </Form.Item>
```

(Use `InputNumber` since the field is now int.)

**Step 6:** Update `handleDelete` (lines 205–213):

```typescript
  const handleDelete = async (materialId: number) => {
    try {
      await api.delete(`/basicdata/materials/${materialId}`)
      message.success('删除成功')
      refreshAll()
    } catch (error) {
      message.error('删除失败')
    }
  }
```

**Step 7:** Update `handleSubmit` (lines 215–235). Change:

```typescript
      if (editingItem) {
        if (values.parent_id === editingItem.material_id) {
          message.error('上级物料不能选择自身')
          return
        }
        await api.put(`/basicdata/materials/${editingItem.material_id}`, values)
```

to:

```typescript
      if (editingItem) {
        if (values.parent_id === editingItem.erp_material_id) {
          message.error('上级物料不能选择自身')
          return
        }
        await api.put(`/basicdata/materials/${editingItem.erp_material_id}`, values)
```

**Step 8:** Update the columns array (line 238). Change:

```typescript
    { title: '物料ID', dataIndex: 'material_id', key: 'material_id', width: 120 },
```

to:

```typescript
    { title: 'ERP物料ID', dataIndex: 'erp_material_id', key: 'erp_material_id', width: 120 },
```

**Step 9:** Update the delete confirm (line 270). Change:

```tsx
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.material_id)} okText="确认" cancelText="取消">
```

to:

```tsx
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.erp_material_id)} okText="确认" cancelText="取消">
```

**Step 10:** Update the modal tree prop (line 343). Change:

```tsx
        <MaterialForm form={form} treeData={editingItem ? filterSelfFromTree(parentTreeData, editingItem.material_id) : parentTreeData} />
```

to:

```tsx
        <MaterialForm form={form} treeData={editingItem ? filterSelfFromTree(parentTreeData, editingItem.erp_material_id) : parentTreeData} />
```

**Step 11:** Verify with the only typecheck command.

```bash
cd frontend && npm run build
```

Expected output: build succeeds (no TypeScript errors). Warnings about unused imports are fine; this project has `noUnusedLocals: false` per AGENTS.md.

---

## Task 11: Final verification sweep

**Step 1:** Sweep for any leftover references in backend code.

```bash
cd backend && grep -rn "Material\.material_id" app/
```

Expected output: empty (no matches).

```bash
cd backend && grep -rn "scm_material.*material_id[^=]" app/ alembic/versions/ 2>/dev/null | grep -v "erp_material_id" | grep -v "scm_material_id\|inventory\|mrp\|demand"
```

Expected output: empty (no other code references the renamed field).

**Step 2:** Frontend typecheck.

```bash
cd frontend && npm run build
```

Expected output: build succeeds.

**Step 3:** Run init_database.py against the dev DB (or local PostgreSQL). It's idempotent; the migration will run on the first start and be a no-op on subsequent runs.

```bash
cd backend && python init_database.py
```

Expected output includes the lines:
```
Migrating scm_material to erp_material_id (int)...
  scm_material: material_id -> erp_material_id (int)
  scm_material.parent_id -> integer
  scm_bom.material_id -> integer
  scm_bom_detail.material_id -> integer
scm_material erp_material_id migration done
```

(Or "already exists, skip rename" if the DB is already migrated.)

**Step 4:** Run alembic upgrade.

```bash
cd backend && alembic upgrade head
```

Expected: applies `rename_scm_material_erp_id` cleanly. (If the DB was already migrated by init_database.py, the `ALTER COLUMN ... TYPE INTEGER` is a no-op and the `RENAME COLUMN` will fail because the source column doesn't exist. To handle this, run alembic first on a fresh DB, or accept that init_database.py is the authoritative run; the alembic migration is for ad-hoc / external environments.)

**Step 5:** Smoke test the API.

```bash
curl -X POST http://localhost:8000/api/v1/basicdata/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "login_type=employee&username=admin&password=admin123"
```

(Capture the token, then:)

```bash
curl http://localhost:8000/api/v1/basicdata/materials/tree -H "Authorization: Bearer $TOKEN"
```

Expected: 200 with `{code: 0, data: [...]}`, the tree nodes have `erp_material_id` (int) and `parent_id` (int|null).

---

## Notes for the user

- **ERP `field_mapping` table**: After applying the migration, update the row for `materials_masterdata` so the source SQL column `material_id` maps to the model field `erp_material_id` instead of `material_id`. This is runtime DB data; no code change is needed.
- **External API consumers** of `GET /api/v1/basicdata/masterdata/materials/list` will see the response key change from `material_id` to `erp_material_id`. Coordinate with downstream teams if needed.
- **scm_bom.parent_material_id** is left as VARCHAR(50) intentionally — it's not joined to scm_material anywhere in the current codebase.
