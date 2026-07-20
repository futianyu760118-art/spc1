# 滚动态基准库存 (Rolling Available Stock) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `available_qty` column to `scm_inventory_check_item`. On check completion, compute `available_qty = system_qty - req_qty + actual_qty` and store it. On new check creation, the `system_qty` for each material is the latest `available_qty` from a prior completed check, falling back to `scm_inventory.qty_on_hand` when no prior check exists. Frontend: rename "库存数" → "可用库存", add "盘后可用" preview column, validate `actual_qty` before allowing completion.

**Architecture:** Add 1 column + 1 helper SQL query. The "推叠" model is implemented as: completion writes `available_qty`; creation reads the latest completed `available_qty` per material via `DISTINCT ON (material_id) ORDER BY completed_at DESC`. No write to `scm_inventory.qty_on_hand`. No schema-destructive migrations (only `ADD COLUMN IF NOT EXISTS`).

**Tech Stack:** FastAPI + SQLAlchemy 2 (async) + Pydantic v2 + PostgreSQL (`DISTINCT ON`). React + Ant Design 5. Python 3.12, Node 20.

## Global Constraints

- `get_db()` from `app/core/database.py` auto-commits on success / rolls back on exception; do not call `db.commit()` manually inside endpoints.
- New column is added by `Base.metadata.create_all` for fresh tables AND by an entry in `init_database.py`'s `migrate_columns` dict for existing tables.
- `npm run build` is the **only** typecheck (per AGENTS.md).
- Add comments only when explicitly requested.
- Response envelopes must be `ResponseModel[T]` (`{code, message, data}`).

---

## Task 1: Backend model — add `available_qty` column

**Files:**
- Modify: `backend/app/models/material/inventory_check.py`
- Modify: `backend/init_database.py` (`migrate_columns` dict)

**Step 1: Add the column to the StockCheckItem model**

Edit `D:\wanghuazheng\project\SPC-v2\backend\app\models\material\inventory_check.py`. Find the `class StockCheckItem(Base):` block. After the `diff_qty = Column(Numeric(18, 4), nullable=False, default=0, comment="差异数=actual-system")` line, add a new column:

```python
    available_qty = Column(Numeric(18, 4), nullable=True, comment="完结时计算:system_qty - req_qty + actual_qty(作为下一张单 system_qty 的来源)")
```

(Insert it right after `diff_qty`, before `is_checked`.)

**Step 2: Register the column in `init_database.py` migrate_columns**

In `D:\wanghuazheng\project\SPC-v2\backend\init_database.py`, find the `new_columns` dict (a top-level `dict` near line 101-300). Add a new key `"scm_inventory_check_item"` with the available_qty entry. The exact location doesn't matter as long as the dict is at the top level. Place it alphabetically near the other `_item` tables.

Add a new entry:
```python
    "scm_inventory_check_item": {
        "available_qty": "NUMERIC(18,4)",
    },
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.models.material.inventory_check import StockCheck, StockCheckItem; print(StockCheckItem.__table__.columns['available_qty'].type, StockCheckItem.__table__.columns['available_qty'].nullable)"
```
Expected: `NUMERIC(18, 4) True`

Then run init to actually create the column:
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" init_database.py
```
Expected: prints progress, no error, idempotent (re-runnable).

Verify via direct DB query (optional):
```bash
& "D:\software\miniconda3\python.exe" -c "
import asyncio
from app.core.database import engine
from sqlalchemy import text
async def check():
    async with engine.connect() as c:
        r = await c.execute(text(\"SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='scm_inventory_check_item' AND column_name='available_qty'\"))
        print([dict(row._mapping) for row in r])
    await engine.dispose()
asyncio.run(check())
"
```
Expected: `[{column_name: 'available_qty', data_type: 'numeric', is_nullable: 'YES'}]`

---

## Task 2: Pydantic schema — add `available_qty` to `StockCheckItemOut`

**Files:**
- Modify: `backend/app/schemas/material/stock_check.py`

**Step 1: Add the field to `StockCheckItemOut`**

In `D:\wanghuazheng\project\SPC-v2\backend\app\schemas\material\stock_check.py`, find the `class StockCheckItemOut(BaseModel):` block. After the `diff_qty` line, add:

```python
    available_qty: Optional[Decimal] = None
```

(So the field reads as `actual_qty → diff_qty → available_qty`.)

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.schemas.material.stock_check import StockCheckItemOut; m = StockCheckItemOut(id=1, check_id=1, available_qty=123.45); print(m.available_qty)"
```
Expected: `123.45`

---

## Task 3: Service — add helper + modify create/complete

**Files:**
- Modify: `backend/app/services/material/stock_check_service.py`

**Step 1: Add new helper `_get_available_by_material_id`**

In `D:\wanghuazheng\project\SPC-v2\backend\app\services\material\stock_check_service.py`, after the existing `_get_stock_by_material_id` function (lines ~24-37), add:

```python
async def _get_available_by_material_id(
    db: AsyncSession,
    material_ids: List[int],
) -> Dict[int, Decimal]:
    """按 material_id 取最近一次 completed 盘点单产生的 available_qty (= system_qty - req_qty + actual_qty)。
    未命中的 material_id 不在 dict 中,调用方需 fallback 到 _get_stock_by_material_id (qty_on_hand)。"""
    if not material_ids:
        return {}
    result = await db.execute(
        select(
            StockCheckItem.material_id,
            StockCheckItem.available_qty,
        )
        .join(StockCheck, StockCheck.id == StockCheckItem.check_id)
        .where(
            StockCheckItem.material_id.in_(material_ids),
            StockCheck.status == 'completed',
            StockCheckItem.available_qty.is_not(None),
        )
        .order_by(StockCheckItem.material_id, StockCheck.completed_at.desc())
        .distinct(StockCheckItem.material_id)
    )
    return {
        row.material_id: Decimal(str(row.available_qty))
        for row in result
        if row.available_qty is not None
    }
```

(Add the necessary imports if missing: `Dict` and `select`. The current import line has `from typing import Optional, List, Dict` already.)

**Step 2: Modify `create_stock_check_from_order` to use the helper**

Find the `create_stock_check_from_order` function. Currently it does:
```python
stock_map = await _get_stock_by_material_id(db, list(agg.keys()))
```

Replace it with:
```python
    available_map = await _get_available_by_material_id(db, list(agg.keys()))
    stock_map = await _get_stock_by_material_id(db, list(agg.keys()))

    # 优先用最近一次完成单的 available_qty,缺时回退到 qty_on_hand
    effective_system_qty: Dict[int, Decimal] = {}
    for mid, qoh in stock_map.items():
        if mid in available_map:
            effective_system_qty[mid] = Decimal(str(available_map[mid]))
        else:
            effective_system_qty[mid] = qoh
```

Then in the item-row construction loop (where `sys_q = stock_map.get(mid, Decimal("0"))`), replace:
```python
        sys_q = stock_map.get(mid, Decimal("0"))
```
with:
```python
        sys_q = effective_system_qty.get(mid, Decimal("0"))
```

**Step 3: Modify `complete_stock_check` to compute and validate**

Find the `complete_stock_check` function. After the existing checks (status, total, checked) and BEFORE setting `head.status = "completed"`, add:

```python
    for item in head.items:
        if item.actual_qty is None:
            raise ValueError(f"物料 {item.material_code or item.material_id} 还未录入实盘数,请先填写再完结")
        if item.system_qty is not None and item.req_qty is not None:
            item.available_qty = (
                Decimal(str(item.system_qty))
                - Decimal(str(item.req_qty))
                + Decimal(str(item.actual_qty))
            )
```

So the `complete_stock_check` function body becomes (after the change):
```python
async def complete_stock_check(db: AsyncSession, check_id: int, current_user: dict) -> StockCheck:
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if head.status == "cancelled":
        raise ValueError("已取消的盘点单不能完结")
    if head.status == "completed":
        raise ValueError("已完结的盘点单不能再次完结")
    items_res = await db.execute(
        select(StockCheckItem).where(StockCheckItem.check_id == check_id).order_by(StockCheckItem.id)
    )
    head.items = list(items_res.scalars().all())
    total = (await db.execute(
        select(func.count(StockCheckItem.id)).where(StockCheckItem.check_id == check_id)
    )).scalar_one()
    checked = (await db.execute(
        select(func.count(StockCheckItem.id)).where(
            StockCheckItem.check_id == check_id, StockCheckItem.is_checked == 1
        )
    )).scalar_one()
    if int(total or 0) == 0:
        raise ValueError("盘点单无物料行,无法完结")
    if int(checked or 0) < int(total or 0):
        raise ValueError(f"还有 {int(total) - int(checked)} 行未盘点,无法完结")

    for item in head.items:
        if item.actual_qty is None:
            raise ValueError(f"物料 {item.material_code or item.material_id} 还未录入实盘数,请先填写再完结")
        if item.system_qty is not None and item.req_qty is not None:
            item.available_qty = (
                Decimal(str(item.system_qty))
                - Decimal(str(item.req_qty))
                + Decimal(str(item.actual_qty))
            )

    head.status = "completed"
    head.completed_at = datetime.utcnow()
    head.checked_by = current_user.get("username", "")
    await db.flush()
    return head
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.services.material.stock_check_service import create_stock_check_from_order, complete_stock_check, _get_available_by_material_id; print('ok')"
```
Expected: `ok`

```bash
& "D:\software\miniconda3\python.exe" -c "from app.main import app; print(len([r for r in app.routes if 'stock-check' in r.path]))"
```
Expected: `9` (no API surface change)

---

## Task 4: Frontend — rename column + add preview + validation

**Files:**
- Modify: `frontend/src/pages/OrderDelivery/StockCheck/index.tsx`

**Step 1: Rename "库存数" column header to "可用库存"**

In `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\OrderDelivery\StockCheck\index.tsx`, find the column with `title: '库存数'`. Change it to `title: '可用库存'`. The dataIndex stays `system_qty`.

**Step 2: Add "盘后可用" column after the "差异" column**

Find the "差异" column block. After it, add a new column definition:

```tsx
    {
      title: '盘后可用', key: 'available', width: 110, align: 'right' as const,
      render: (_: any, r: StockCheckItem) => {
        const sys = r.system_qty != null ? Number(r.system_qty) : 0
        const req = r.req_qty != null ? Number(r.req_qty) : 0
        const act = r.actual_qty != null ? Number(r.actual_qty) : null
        if (act == null) return <span style={{ color: '#94a3b8' }}>-</span>
        const available = sys - req + act
        const color = available > sys ? '#16a34a' : available < sys ? '#dc2626' : '#64748b'
        return <span style={{ color, fontWeight: 500 }}>{available.toFixed(2)}</span>
      },
    },
```

**Step 3: Add validation to `handleComplete` and disable `is_checked` when actual_qty is null**

Find the `handleComplete` `useCallback`. Modify it to pre-check:

```tsx
  const handleComplete = useCallback(async () => {
    if (!activeCheck) return
    const incomplete = items.filter(it => it.actual_qty == null)
    if (incomplete.length > 0) {
      message.error(`还有 ${incomplete.length} 行未录入实盘数,请先填写后再标记完成`)
      return
    }
    Modal.confirm({
      title: '标记完成',
      content: '完结后所有行将不可再修改,确认继续?',
      onOk: async () => {
        try {
          const res: any = await materialApi.completeStockCheck(activeCheck.id)
          setActiveCheck(res.data)
          setItems(res.data.items || [])
          message.success('已完结')
        } catch (e: any) {
          message.error(e?.response?.data?.detail || e.message || '完结失败')
        }
      },
    })
  }, [activeCheck, items])
```

Find the "已盘" column in the `columns` array. Modify the Checkbox to disable when `actual_qty` is null:

```tsx
    {
      title: '已盘', dataIndex: 'is_checked', width: 70, align: 'center' as const,
      render: (_: any, r: StockCheckItem) => (
        <Checkbox
          disabled={readonly || r.actual_qty == null}
          checked={r.is_checked === 1}
          onChange={(e) => updateItem(r.id, { is_checked: e.target.checked ? 1 : 0 })}
        />
      ),
    },
```

**Step 4: Update StockCheckItem interface to include `available_qty`**

Find the `interface StockCheckItem` block. Add the field:

```tsx
  available_qty?: number | null
```

(Add it after `diff_qty`.)

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npm run build 2>&1 | Select-String "error|built" | Select-Object -First 5
```
Expected: `built in <time>` with no `error` lines.

---

## Task 5: End-to-end smoke test (cross-order chain)

**Files:**
- Create: `backend/_smoke_rolling.py` (test script, will be deleted after)

**Step 1: Create the test script**

Create `D:\wanghuazheng\project\SPC-v2\backend\_smoke_rolling.py`:

```python
"""Cross-order rolling available stock smoke test.

Verifies the chain: A 完结 → available_qty 入链 → B 创建时 system_qty 来自 A。
"""

import os
import subprocess
import time
import urllib.request
import urllib.error
import json

PORT = 8001
LOG = os.path.join(os.environ.get("TEMP", r"C:\Users\hjxsz\AppData\Local\Temp"), "opencode", "rolling-smoke.log")
PROC = None


def start():
    global PROC
    open(LOG, "w").close()
    PROC = subprocess.Popen(
        [r"D:\software\miniconda3\python.exe", "-m", "uvicorn", "app.main:app",
         f"--port={PORT}", "--host=127.0.0.1", "--log-level=warning"],
        cwd=r"D:\wanghuazheng\project\SPC-v2\backend",
        stdout=subprocess.DEVNULL,
        stderr=open(LOG, "w"),
    )
    time.sleep(10)


def stop():
    if PROC:
        PROC.terminate()
        try: PROC.wait(timeout=5)
        except: PROC.kill()


def call(method, path, token=None, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=body,
        headers={"Authorization": f"Bearer {token}"} | ({"Content-Type": "application/json"} if body else {}),
        method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def login():
    data = b"login_type=employee&username=admin&password=admin123"
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/v1/basicdata/auth/login",
        data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())["data"]["access_token"]


def find_order_with_material(token):
    orders = call("GET", "/api/v1/orders?page=1&page_size=20", token)
    for o in orders["data"]["items"]:
        mats = call("GET", f"/api/v1/orders/{o['order_no']}/product-materials", token)
        if any(x.get("materials") for x in mats.get("data", [])):
            return o["order_no"]
    return None


def main():
    start()
    try:
        token = login()
        order_no = find_order_with_material(token)
        if not order_no:
            print("No order with materials found")
            return
        print(f"[1] Using order: {order_no}")

        # A: create + check all items + complete
        created_a = call("POST", f"/materials/stock-check/from-order/{order_no}", token, {"order_no": order_no})
        check_a = created_a["data"]
        items_a = check_a["items"]
        mid = items_a[0]["material_id"]
        sys_a = float(items_a[0]["system_qty"])
        req_a = float(items_a[0]["req_qty"])
        print(f"[2] Order A created {check_a['check_no']}: mid={mid}, system_qty={sys_a}, req={req_a}")
        actual_a = 1234.5
        for it in items_a:
            call("PUT", f"/materials/stock-check/items/{it['id']}", token,
                 {"actual_qty": actual_a, "is_checked": 1, "remark": "A"})
        completed_a = call("POST", f"/materials/stock-check/{check_a['id']}/complete", token)
        avail_a = float(completed_a["data"]["items"][0]["available_qty"])
        expected_avail_a = sys_a - req_a + actual_a
        match_a = abs(avail_a - expected_avail_a) < 0.001
        print(f"[3] A completed: available_qty={avail_a} (expected {expected_avail_a}) {'PASS' if match_a else 'FAIL'}")

        # B: create + check first item's system_qty should come from A's available
        created_b = call("POST", f"/materials/stock-check/from-order/{order_no}", token, {"order_no": order_no})
        check_b = created_b["data"]
        first_b = next((it for it in check_b["items"] if it["material_id"] == mid), None)
        if not first_b:
            print(f"[4] FAIL: material {mid} not in B's items")
            return
        sys_b = float(first_b["system_qty"])
        print(f"[4] B created: mid={mid}, system_qty={sys_b} (expected {avail_a}) {'PASS' if abs(sys_b - avail_a) < 0.001 else 'FAIL'}")

        print("\n=== ROLLING SMOKE TEST COMPLETED ===")
    finally:
        stop()


if __name__ == "__main__":
    main()
```

**Step 2: Run the test**

```bash
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force
& "D:\software\miniconda3\python.exe" _smoke_rolling.py 2>&1 | Select-Object -First 20
```

Expected output:
```
[1] Using order: HJY20251212-334
[2] Order A created PD...: mid=65209, system_qty=357, req=4
[3] A completed: available_qty=1587.5 (expected 1587.5) PASS
[4] B created: mid=65209, system_qty=1587.5 (expected 1587.5) PASS
=== ROLLING SMOKE TEST COMPLETED ===
```

**Step 3: Delete the test script**

```bash
Remove-Item -LiteralPath "D:\wanghuazheng\project\SPC-v2\backend\_smoke_rolling.py" -Force
```

---

## Task 6: Final build + verify

**Step 1: Frontend build**

```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npm run build 2>&1 | Select-String "error|built" | Select-Object -First 5
```
Expected: `built in <time>` with no `error` lines.

**Step 2: Backend import + route check**

```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.main import app; print(len([r for r in app.routes if 'stock-check' in r.path]))"
```
Expected: `9`

**Step 3: Re-run init_database.py to confirm idempotent**

```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" init_database.py 2>&1 | Select-Object -Last 5
```
Expected: "Database initialization completed successfully!"

**Step 4: Confirm no leftover test files**

```bash
Get-ChildItem -LiteralPath "D:\wanghuazheng\project\SPC-v2\backend" -Filter "_*.py" -ErrorAction SilentlyContinue | Select-Object Name
```
Expected: empty.

---

## Done criteria

- [ ] `StockCheckItem.available_qty` column added to model + Pydantic schema
- [ ] `init_database.py` migrate_columns registers the new column; running is idempotent
- [ ] `_get_available_by_material_id` helper queries latest completed `available_qty` per material
- [ ] `create_stock_check_from_order` uses `available_qty` when present, falls back to `qty_on_hand`
- [ ] `complete_stock_check` validates all `actual_qty` non-null, computes and stores `available_qty`
- [ ] Frontend: "库存数" → "可用库存"; new "盘后可用" preview column; `is_checked` disabled when `actual_qty` null; handleComplete pre-checks
- [ ] `npm run build` passes
- [ ] End-to-end smoke test: A completed → B's `system_qty` matches A's `available_qty`
- [ ] No leftover `_smoke_*.py` or `_verify_*.py` test scripts in backend/
