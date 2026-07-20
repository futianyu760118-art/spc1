# 物料历史盘点 Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a per-row "查询" icon to the StockCheck materials table. Clicking opens a side Drawer listing all historical stock checks that included the selected material, with order_no and customer visible.

**Architecture:** 1 new backend GET endpoint, 1 new service function, 1 new Pydantic schema, 1 new api client method, 1 new Drawer in the StockCheck page. Read-only — no mutations to `scm_inventory_check` or `scm_inventory_check_item`.

**Tech Stack:** FastAPI + SQLAlchemy 2 (async) + Pydantic v2 + PostgreSQL. React + Ant Design 5 (`Drawer` + `Table` + `Empty`).

## Global Constraints

- `npm run build` is the only typecheck.
- All backend responses use `ResponseModel[T]`.
- Add comments only when explicitly requested.
- New column types: nullable everywhere reasonable.

---

## Task 1: Pydantic schema — add `MaterialHistoryItem`

**Files:**
- Modify: `backend/app/schemas/material/stock_check.py`

**Step 1: Append the new model**

In `D:\wanghuazheng\project\SPC-v2\backend\app\schemas\material\stock_check.py`, after the `StockCheckListOut` class, append:

```python


class MaterialHistoryItem(BaseModel):
    check_no: str
    order_no: str
    customer: Optional[str] = None
    status: str
    check_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    actual_qty: Optional[Decimal] = None
    available_qty: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.schemas.material.stock_check import MaterialHistoryItem; m = MaterialHistoryItem(check_no='PD1', order_no='HJ1', status='completed', customer='客户A', actual_qty=950, available_qty=450); print('ok', m.customer, m.actual_qty)"
```
Expected: `ok 客户A 950`

---

## Task 2: Service function — `get_material_history`

**Files:**
- Modify: `backend/app/services/material/stock_check_service.py`

**Step 1: Append the new function**

In `D:\wanghuazheng\project\SPC-v2\backend\app\services\material\stock_check_service.py`, append at the end of the file:

```python


async def get_material_history(
    db: AsyncSession,
    material_id: int,
    limit: int = 100,
) -> List[Dict]:
    """查询某物料被哪些盘点单盘点过的历史记录 (含已完成/进行中/已取消)。
    返回字典列表,字段与 MaterialHistoryItem 一致;含 customer 来自 sale_order。"""
    sql = (
        select(
            StockCheck.check_no,
            StockCheck.order_no,
            StockCheck.status,
            StockCheck.check_date,
            StockCheck.completed_at,
            StockCheck.created_at,
            StockCheck.created_by,
            StockCheckItem.actual_qty,
            StockCheckItem.available_qty,
        )
        .join(StockCheck, StockCheck.id == StockCheckItem.check_id)
        .where(StockCheckItem.material_id == material_id)
        .order_by(StockCheck.completed_at.desc().nulls_last(), StockCheck.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(sql)).all()

    if not rows:
        return []

    order_nos = sorted({r.order_no for r in rows if r.order_no})
    customer_map: Dict[str, Optional[str]] = {}
    if order_nos:
        from app.models.order.sale_order import SaleOrder
        so_rows = (await db.execute(
            select(SaleOrder.order_no, SaleOrder.customer)
            .where(SaleOrder.order_no.in_(order_nos))
        )).all()
        for so_r in so_rows:
            customer_map.setdefault(so_r.order_no, so_r.customer)

    return [
        {
            "check_no": r.check_no,
            "order_no": r.order_no,
            "customer": customer_map.get(r.order_no),
            "status": r.status,
            "check_date": r.check_date,
            "completed_at": r.completed_at,
            "actual_qty": r.actual_qty,
            "available_qty": r.available_qty,
            "created_at": r.created_at,
            "created_by": r.created_by,
        }
        for r in rows
    ]
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.services.material.stock_check_service import get_material_history; print('ok')"
```
Expected: `ok`

---

## Task 3: API endpoint

**Files:**
- Modify: `backend/app/api/v1/material/stock_check.py`

**Step 1: Add imports and endpoint**

In `D:\wanghuazheng\project\SPC-v2\backend\app\api\v1\material\stock_check.py`:

Add to the imports from `app.schemas.material.stock_check` (top of file):

```python
from app.schemas.material.stock_check import (
    StockCheckCreate,
    StockCheckOut,
    StockCheckListOut,
    StockCheckItemOut,
    StockCheckItemUpdate,
    StockCheckItemBatchUpdate,
    MaterialHistoryItem,
)
```

(If `MaterialHistoryItem` is missing from the list, add it.)

Add to the imports from `app.services.material.stock_check_service`:

```python
from app.services.material.stock_check_service import (
    create_stock_check_from_order,
    update_stock_check_item,
    batch_update_items,
    complete_stock_check,
    cancel_stock_check,
    get_stock_check_with_items,
    list_recent_stock_checks,
    list_stock_checks_by_order,
    get_material_history,
)
```

(Add `get_material_history` to the import list.)

Append the new endpoint at the end of the file (before any trailing line):

```python


@router.get("/stock-check/material-history", response_model=ResponseModel[list[MaterialHistoryItem]])
async def get_material_history_view(
    material_id: int = Query(..., description="物料ID"),
    current_user: dict = Depends(PermissionChecker("orders.stock_check", "read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_material_history(db, material_id=material_id)
    return ResponseModel(data=[MaterialHistoryItem(**r) for r in rows])
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.main import app; print(len([r for r in app.routes if 'stock-check' in r.path]))"
```
Expected: `10` (was 9, +1 for the new endpoint)

---

## Task 4: API client — `getMaterialHistory`

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: Add the new method**

In `D:\wanghuazheng\project\SPC-v2\frontend\src\services\api.ts`, inside the `materialApi` object, after the last stock-check related method (`cancelStockCheck`), add:

```ts
  getMaterialHistory: (params: { material_id: number }) =>
    api.get('/materials/stock-check/material-history', { params }),
```

**Verification:**
```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npx tsc --noEmit -p tsconfig.json 2>&1 | Select-String "getMaterialHistory" | Select-Object -First 5
```
Expected: no errors.

---

## Task 5: Frontend — icon column + Drawer in StockCheck page

**Files:**
- Modify: `frontend/src/pages/OrderDelivery/StockCheck/index.tsx`

**Step 1: Add imports**

In `D:\wanghuazheng\project\SPC-v2\frontend\src\pages\OrderDelivery\StockCheck\index.tsx`:

Update the `antd` imports — add `Drawer, Empty`:

```tsx
import {
  Table, Input, Button, Space, Tag, message, Modal, Card, Row, Col,
  InputNumber, Checkbox, Spin, Popover, Tour, Drawer, Empty,
} from 'antd'
```

Update the `@ant-design/icons` imports — add `HistoryOutlined`:

```tsx
import { SearchOutlined, ReloadOutlined, CheckCircleOutlined, StopOutlined, ArrowLeftOutlined, SaveOutlined, QuestionCircleOutlined, HistoryOutlined } from '@ant-design/icons'
```

**Step 2: Add a type for history item**

After the `StockCheckItem` interface (around line 30), add:

```tsx
interface MaterialHistoryItem {
  check_no: string
  order_no: string
  customer?: string | null
  status: string
  check_date?: string | null
  completed_at?: string | null
  actual_qty?: number | null
  available_qty?: number | null
  created_at?: string | null
  created_by?: string | null
}
```

**Step 3: Add state and handler**

After the existing tour-related state (after `const [tourOpen, setTourOpen] = useState(false)`), add:

```tsx
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false)
  const [historyMaterial, setHistoryMaterial] = useState<StockCheckItem | null>(null)
  const [historyItems, setHistoryItems] = useState<MaterialHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const openMaterialHistory = useCallback(async (r: StockCheckItem) => {
    if (!r.material_id) {
      message.warning('该物料无 ID,无法查询历史')
      return
    }
    setHistoryMaterial(r)
    setHistoryDrawerOpen(true)
    setHistoryLoading(true)
    try {
      const res: any = await materialApi.getMaterialHistory({ material_id: r.material_id })
      setHistoryItems(res.data || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载历史盘点失败')
    } finally {
      setHistoryLoading(false)
    }
  }, [])
```

**Step 4: Add the icon column to the materials table**

In the `columns` `useMemo` array, find the "标记时间" column (or any column before "操作"). Add a new column "历史" right after it:

```tsx
    {
      title: '历史', key: 'history', width: 70, align: 'center' as const, fixed: 'right' as const,
      render: (_: any, r: StockCheckItem) => (
        <Tooltip title="查看该物料被哪些盘点单盘点过">
          <Button
            type="link" size="small" icon={<HistoryOutlined />}
            onClick={() => openMaterialHistory(r)}
          />
        </Tooltip>
      ),
    },
```

**Step 5: Add the Drawer at the end of the page render**

Find the closing of the main return statement, right after the `<Tour>` component (the very last element before the closing `</div>`), add the `<Drawer>`:

```tsx
      <Drawer
        title={historyMaterial ? `物料 ${historyMaterial.material_code} 历史盘点记录` : '历史盘点记录'}
        open={historyDrawerOpen}
        onClose={() => setHistoryDrawerOpen(false)}
        width={760}
      >
        {historyLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : historyItems.length === 0 ? (
          <Empty description="暂无历史盘点记录" />
        ) : (
          <Table
            rowKey="check_no"
            dataSource={historyItems}
            pagination={false}
            size="small"
            columns={[
              { title: '盘点单号', dataIndex: 'check_no', width: 160 },
              { title: '订单号', dataIndex: 'order_no', width: 160 },
              { title: '客户', dataIndex: 'customer', width: 140, ellipsis: true,
                render: v => v || '-' },
              { title: '状态', dataIndex: 'status', width: 90,
                render: v => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.label || v}</Tag> },
              { title: '实盘数', dataIndex: 'actual_qty', width: 100, align: 'right' as const,
                render: v => v != null ? Number(v).toFixed(2) : '-' },
              { title: '盘后可用', dataIndex: 'available_qty', width: 110, align: 'right' as const,
                render: v => v != null ? Number(v).toFixed(2) : '-' },
              { title: '完结时间', dataIndex: 'completed_at', width: 160,
                render: v => v ? formatDateTime(v) : '-' },
            ]}
            scroll={{ x: 1000 }}
          />
        )}
      </Drawer>
```

**Step 6: Build verification**

```bash
cd D:\wanghuazheng\project\SPC-v2\frontend
npm run build 2>&1 | Select-String "error|built" | Select-Object -First 5
```
Expected: `built in <time>` with no `error` lines.

---

## Task 6: End-to-end smoke test

**Files:**
- Create: `backend/_smoke_history.py` (delete after)

**Step 1: Create the test script**

Create `D:\wanghuazheng\project\SPC-v2\backend\_smoke_history.py`:

```python
"""Smoke test for material history endpoint."""

import os, subprocess, time, urllib.request, urllib.error, json

PORT = 8001
LOG = os.path.join(os.environ.get("TEMP", r"C:\Users\hjxsz\AppData\Local\Temp"), "opencode", "history-smoke.log")
PROC = None

def start():
    global PROC
    open(LOG, "w").close()
    PROC = subprocess.Popen(
        [r"D:\software\miniconda3\python.exe", "-m", "uvicorn", "app.main:app",
         f"--port={PORT}", "--host=127.0.0.1", "--log-level=warning"],
        cwd=r"D:\wanghuazheng\project\SPC-v2\backend",
        stdout=subprocess.DEVNULL, stderr=open(LOG, "w"))
    time.sleep(10)

def stop():
    if PROC:
        PROC.terminate()
        try: PROC.wait(timeout=5)
        except: PROC.kill()

def call(method, path, token=None, data=None):
    headers = {}
    if token: headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    if body: headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/v1{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def login():
    data = b"login_type=employee&username=admin&password=admin123"
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/v1/basicdata/auth/login",
        data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())["data"]["access_token"]

def main():
    start()
    try:
        token = login()
        # Material 65209 was used in many smoke tests earlier
        res = call("GET", "/materials/stock-check/material-history?material_id=65209", token)
        items = res.get("data", [])
        print(f"[1] material_id=65209: returned {len(items)} history items")
        if items:
            print(f"    first: {items[0]['check_no']} | {items[0]['order_no']} | {items[0]['customer']} | {items[0]['status']}")
            if items[0]['completed_at']:
                print(f"    completed_at: {items[0]['completed_at']}")
            print(f"    actual_qty: {items[0]['actual_qty']}, available_qty: {items[0]['available_qty']}")
        # Test for a material that has no history
        res2 = call("GET", "/materials/stock-check/material-history?material_id=99999999", token)
        items2 = res2.get("data", [])
        print(f"[2] material_id=99999999 (no history): returned {len(items2)} items (expected 0)")

        if len(items) > 0 and len(items2) == 0:
            print("\n=== HISTORY ENDPOINT VERIFIED ===")
        else:
            print("\n=== HISTORY ENDPOINT FAILED ===")
    finally:
        stop()

if __name__ == "__main__":
    main()
```

**Step 2: Run the test**

```bash
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force
& "D:\software\miniconda3\python.exe" _smoke_history.py 2>&1 | Select-Object -First 15
```

Expected output:
```
[1] material_id=65209: returned 1+ history items
    first: PD... | HJY20251212-334 | None or <customer> | completed
[2] material_id=99999999 (no history): returned 0 items (expected 0)
=== HISTORY ENDPOINT VERIFIED ===
```

**Step 3: Delete the test script**

```bash
Remove-Item -LiteralPath "D:\wanghuazheng\project\SPC-v2\backend\_smoke_history.py" -Force
```

---

## Task 7: Final cleanup + verify

```bash
# Ensure no leftover test scripts
Get-ChildItem -LiteralPath "D:\wanghuazheng\project\SPC-v2\backend" -Filter "_*.py" -ErrorAction SilentlyContinue | Select-Object Name
# Expected: empty

# Stop any uvicorn
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force
```

---

## Done criteria

- [ ] `MaterialHistoryItem` added to Pydantic schema
- [ ] `get_material_history` service function queries `scm_inventory_check_item` JOIN `scm_inventory_check` + `sale_order` for customer
- [ ] `GET /api/v1/materials/stock-check/material-history` endpoint registered
- [ ] `materialApi.getMaterialHistory` added to api client
- [ ] StockCheck page has per-row "历史" icon column + side Drawer
- [ ] Drawer shows 订单号 + 客户 + 状态 + 实盘数 + 盘后可用 + 完结时间
- [ ] Empty state ("暂无历史盘点记录") for materials with no history
- [ ] `npm run build` passes
- [ ] Smoke test passes: returns historical items for a known material, empty for unknown
- [ ] No leftover `_*.py` test scripts
