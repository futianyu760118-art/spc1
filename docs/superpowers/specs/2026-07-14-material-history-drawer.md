# Design: 物料历史盘点侧边抽屉 (Material History Drawer)

**Date:** 2026-07-14
**Status:** Approved, pending implementation
**Scope:** 在物料盘点 (`scm_inventory_check`) 页面,每行物料加"查询"图标 → 点击打开右侧 Drawer → 展示该物料被哪些订单盘点过的历史记录。

---

## 1. Background

仓管员盘点时,需要快速了解:**这个物料之前被哪些订单盘点过**,以辅助:
- 判断"还需不需要再盘"
- 看到历史 actual_qty 与本次对照
- 避免重复关注(同一物料的相邻订单)

现有 UI: `StockCheck/index.tsx` 物料表只展示本次订单的物料(应盘数/可用库存/盘点数/差异/盘后可用/已盘),没有跨订单视角。

---

## 2. 需求

| 项 | 选择 |
|---|---|
| 入口位置 | 物料表每行右侧"查询"图标 |
| 数据范围 | **仅历史盘点** (`scm_inventory_check_item` 关联的盘点单) |
| 展示字段 | **订单号 + 客户**(其他字段可选) |

---

## 3. 数据模型

数据源: `scm_inventory_check_item` JOIN `scm_inventory_check` + 关联 `sale_order` 取 customer。

| 字段 | 来源 | 说明 |
|---|---|---|
| check_no | scm_inventory_check | 盘点单号 |
| order_no | scm_inventory_check | 关联订单 |
| customer | sale_order (correlated subquery) | 客户名 |
| status | scm_inventory_check | completed / in_progress / cancelled |
| check_date | scm_inventory_check | 盘点日期 |
| completed_at | scm_inventory_check | 完结时间 |
| actual_qty | scm_inventory_check_item | 该物料在该盘点的实盘数 |
| available_qty | scm_inventory_check_item | 该物料在该盘点的"盘后可用" |
| created_at | scm_inventory_check | 创建时间 |
| created_by | scm_inventory_check | 创建人 |

按 `completed_at DESC NULLS LAST, created_at DESC` 排序,LIMIT 100。

---

## 4. API 端点

### `GET /api/v1/materials/stock-check/material-history`

**Query**:
- `material_id` (int, required) — 物料 ID

**Response**:
```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "check_no": "PD20260714-001",
      "order_no": "HJY20251212-334",
      "customer": "客户A",
      "status": "completed",
      "check_date": "2026-07-14",
      "completed_at": "2026-07-14T10:00:00",
      "actual_qty": 950.0,
      "available_qty": 450.0,
      "created_at": "2026-07-14T09:30:00",
      "created_by": "admin"
    }
  ]
}
```

**SQL**:
```sql
SELECT 
  sc.check_no, sc.order_no, sc.status, sc.check_date, sc.completed_at,
  sc.created_at, sc.created_by,
  sci.actual_qty, sci.available_qty,
  (SELECT customer FROM sale_order WHERE order_no = sc.order_no LIMIT 1) AS customer
FROM scm_inventory_check_item sci
JOIN scm_inventory_check sc ON sc.id = sci.check_id
WHERE sci.material_id = :material_id
ORDER BY sc.completed_at DESC NULLS LAST, sc.created_at DESC
LIMIT 100
```

**错误处理**:
- 物料 ID 无效:不返回 404,直接返回空数组 (避免暴露 ID 是否存在)
- 内部错误: 500

---

## 5. Pydantic Schema

新文件内容(append 到 `stock_check.py`):

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

---

## 6. 前端 UI

### 6.1 物料表新增"操作"列

在"已盘"列后或"标记时间"列前,新增"操作"列:
- 渲染: `<Button type="link" size="small" icon={<HistoryOutlined />} onClick={() => openMaterialHistory(r)}>`
- 标题: "查看历史盘点"

### 6.2 右侧 Drawer

```tsx
<Drawer
  title={materialHistoryTitle}
  open={historyDrawerOpen}
  onClose={() => setHistoryDrawerOpen(false)}
  width={640}
>
  {historyLoading ? (
    <Spin />
  ) : historyItems.length === 0 ? (
    <Empty description="暂无历史盘点记录" />
  ) : (
    <Table
      dataSource={historyItems}
      columns={[
        { title: '盘点单号', dataIndex: 'check_no', width: 160 },
        { title: '订单号', dataIndex: 'order_no', width: 160 },
        { title: '客户', dataIndex: 'customer', width: 140 },
        { title: '状态', dataIndex: 'status', width: 90,
          render: v => <Tag color={...}>{STATUS_MAP[v]?.label || v}</Tag> },
        { title: '实盘数', dataIndex: 'actual_qty', width: 100, align: 'right',
          render: v => v != null ? Number(v).toFixed(2) : '-' },
        { title: '盘后可用', dataIndex: 'available_qty', width: 110, align: 'right',
          render: v => v != null ? Number(v).toFixed(2) : '-' },
        { title: '完结时间', dataIndex: 'completed_at', width: 160,
          render: v => v ? formatDateTime(v) : '-' },
      ]}
      pagination={false}
      size="small"
    />
  )}
</Drawer>
```

### 6.3 状态

```tsx
const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false)
const [historyMaterial, setHistoryMaterial] = useState<StockCheckItem | null>(null)
const [historyItems, setHistoryItems] = useState<MaterialHistoryItem[]>([])
const [historyLoading, setHistoryLoading] = useState(false)

const openMaterialHistory = useCallback(async (r: StockCheckItem) => {
  if (!r.material_id) return
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

---

## 7. 文件清单 (3 后端 + 1 前端)

| 操作 | 文件 |
|---|---|
| 修改 | `backend/app/schemas/material/stock_check.py` (+ MaterialHistoryItem) |
| 修改 | `backend/app/services/material/stock_check_service.py` (+ get_material_history 函数) |
| 修改 | `backend/app/api/v1/material/stock_check.py` (+ GET endpoint) |
| 修改 | `frontend/src/services/api.ts` (+ getMaterialHistory 方法) |
| 修改 | `frontend/src/pages/OrderDelivery/StockCheck/index.tsx` (+ Drawer + 图标列 + 状态) |
| 新建 | `docs/superpowers/specs/2026-07-14-material-history-drawer.md` (本文档) |
| 新建 | `docs/superpowers/plans/2026-07-14-material-history-drawer.md` |

---

## 8. 验证清单

1. `npm run build` 通过
2. 后端 `from app.main import app` 加载正常,新路由 `/stock-check/material-history` 注册成功
3. Smoke test:
   - 拿一个已被盘点过的物料 (mid=65209)
   - GET `/materials/stock-check/material-history?material_id=65209`
   - 返回 4+ 条历史记录 (按 completed_at DESC)
   - 字段正确 (check_no, order_no, customer, status)
4. UI 验证:
   - 物料表行右侧出现"🔍 历史"图标
   - 点击 → 右侧 Drawer 滑出
   - 列表显示历史盘点 (订单号 + 客户 + 状态)
   - 空物料 → Drawer 显示"暂无历史盘点记录"
   - 关闭 Drawer 不影响物料表

---

## 9. 风险 / 范围外

- **不显示差异列** (差异是 system - actual,需要历史 system_qty;本表只存了 actual,差距难还原)
- **不显示分页** (LIMIT 100,够用)
- **不显示"查看详情"链接** (点击行不跳转;后续按需加)
- **不展示历史中同一订单多次盘点** (直接列表,不去重;用户自己识别)
- **客户为空时显示 "-"**
