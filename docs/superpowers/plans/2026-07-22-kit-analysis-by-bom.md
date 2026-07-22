# 齐套分析 — 按订单下产品 / BOM 视图 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 `/kit-analysis` 页面订单展开行从扁平物料表升级为"产品列表 + 选中产品的 BOM 多级物料齐套表"双栏视图。

**Architecture:** 新增后端端点 `GET /materials/kit-analysis/{order_no}/product-breakdown` 一次性返回该订单的产品列表、每个产品的 BOM 多级树(节点带订单级齐套数字)、未关联 BOM 的孤儿物料。前端重写展开区为左右双栏 + 顶部提示条。BOM 结构复用 `order_materials_service._expand_bom_tree`,齐套数字复用 `kit_analysis_service.get_order_materials`,在 service 层做 join。

**Tech Stack:** FastAPI + async SQLAlchemy(后端),React + TypeScript + Ant Design 5 + Zustand(前端)。无新增依赖。

## Global Constraints

- 后端 Python 3.12,async SQLAlchemy via `get_db()`(auto-commit,不要手动 commit)
- 所有响应必须用 `ResponseModel[T]` 包装(code=0 成功),否则前端 axios 拦截器拒绝
- 路由前缀 `/api/v1`,本端点挂在已存在的 `material.kit_analysis_router` 上,无需改 `__init__.py`
- 权限 key 沿用 `materials.kit_analysis:read`(已在 `init_database.py` 注册)
- 前端 `npm run build` 是**唯一**类型检查,无 lint/test 脚本
- 不修改 `init_database.py`(无新表/无新列)
- 不修改 `MainLayout.tsx` / `App.tsx` / 权限配置(路由/菜单/权限完全复用)
- TS `strict: true`,但 `noUnusedLocals: false`(未使用变量不报错)
- 不加注释,除非用户明确要求

---

## Task 1: 后端 — 新增 Schema

**文件**: `backend/app/schemas/material/schemas.py`

### Step 1.1: 扩展 typing 导入

把第 3 行 `from typing import Optional, List` 改为加 `Dict`:

```python
from typing import Optional, List, Dict
```

### Step 1.2: 在 `KitAnalysisItem` 之后追加新 schema

找到 `KitAnalysisItem` 类定义结尾(约 290-291 行,其后是 `# ============ 供应商风险分析 ============`),在分隔注释**之前**插入:

```python
class BomKitMaterialItem(KitAnalysisMaterialItem):
    """BOM 树节点 + 订单级齐套数字。继承 KitAnalysisMaterialItem 全部字段。"""
    level: int = 1
    bom_id: Optional[str] = None
    standard_qty: Optional[float] = None
    req_qty: Optional[float] = None
    has_sub_bom: bool = False
    children: List["BomKitMaterialItem"] = []


class ProductKitSummary(BaseModel):
    """左栏产品卡片数据。"""
    line_no: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    product_model: Optional[str] = None
    bom_no: Optional[str] = None
    bom_id: Optional[str] = None
    order_qty: Optional[float] = None
    promised_date: Optional[date] = None
    leaf_total: int = 0
    leaf_received: int = 0
    leaf_partial: int = 0
    leaf_not_ordered: int = 0
    leaf_overdue: int = 0
    leaf_stagnant: int = 0
    has_bom: bool = True
    kit_rate: float = 0.0
    risk_level: str = "green"


class OrderProductKitBreakdownOut(BaseModel):
    """新端点的响应体。"""
    order_no: str
    products: List[ProductKitSummary] = []
    orphan_materials: List[KitAnalysisMaterialItem] = []
    bom_trees: Dict[str, List[BomKitMaterialItem]] = {}


BomKitMaterialItem.model_rebuild()
```

### 验证

```powershell
python -c "from backend.app.schemas.material.schemas import BomKitMaterialItem, ProductKitSummary, OrderProductKitBreakdownOut; print('ok')"
```

workdir: `D:\wanghuazheng\project\SPC-v2`

预期输出: `ok`

---

## Task 2: 后端 — 新增 Service 函数

**文件**: `backend/app/services/material/kit_analysis_service.py`

### Step 2.1: 顶部导入补齐

在第 22 行(`from app.schemas.material.schemas import KitAnalysisItem, KitAnalysisMaterialItem`)改为:

```python
from app.schemas.material.schemas import (
    KitAnalysisItem,
    KitAnalysisMaterialItem,
    BomKitMaterialItem,
    ProductKitSummary,
    OrderProductKitBreakdownOut,
)
```

在第 32 行的现有 `from app.services.order.order_materials_service import (...)` 块**末尾**追加 `_expand_bom_tree`(在 `_to_float,` 之后,闭合括号 `)` 之前):

```python
from app.services.order.order_materials_service import (
    STATUS_LABELS,
    _kit_met,
    _material_property_label,
    _status,
    _summarize_pos,
    _to_float,
    _expand_bom_tree,
)
```

### Step 2.2: 在文件末尾追加 service 函数

在文件最后(`get_order_materials` 函数之后)追加:

```python
async def get_order_product_breakdown(
    db: AsyncSession,
    order_no: str,
) -> dict:
    """按订单下产品 + BOM 多级树返回齐套明细。

    一次返回:
      - products: 产品列表(每产品含汇总状态)
      - bom_trees: {product_key: BOM 树},树节点含订单级齐套数字
      - orphan_materials: MrpPlanOrder 中存在但 BOM 未覆盖的物料
    """
    from decimal import Decimal as _Decimal
    from collections import defaultdict

    line_result = await db.execute(
        select(SaleOrderLine)
        .where(SaleOrderLine.order_no == order_no)
        .order_by(SaleOrderLine.id)
    )
    lines = line_result.scalars().all()

    if not lines:
        order_q = await db.execute(select(SaleOrder).where(SaleOrder.order_no == order_no))
        order = order_q.scalar_one_or_none()
        if order:
            lines = [SimpleNamespace(
                order_no=order.order_no,
                line_no=order.line_no,
                product_code=order.product_code,
                product_name=order.product_name,
                product_model=None,
                order_qty=order.order_qty,
                promised_date=order.promised_date,
                bom_id=None,
                bom_no=None,
            )]

    # 1) 订单级齐套数字(扁平),按 material_code 索引
    order_materials = await get_order_materials(db, order_no=order_no)
    mat_by_code: dict[str, KitAnalysisMaterialItem] = {m.material_code: m for m in order_materials}

    # 2) 按 (product_code, bom_id) 分组产品行
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for line in lines:
        line_bom_id = str(line.bom_id) if getattr(line, "bom_id", None) else None
        key = (line.product_code or "", line_bom_id or "")
        groups[key].append(line)

    products: list[ProductKitSummary] = []
    bom_trees: dict[str, list[BomKitMaterialItem]] = {}
    covered_codes: set[str] = set()

    for idx, ((product_code_key, bom_id_key), group_lines) in enumerate(groups.items()):
        first = group_lines[0]
        total_qty = _Decimal("0")
        line_nos: list[str] = []
        promised = None
        for ln in group_lines:
            qty = ln.order_qty if ln.order_qty is not None else 0
            total_qty += _Decimal(str(qty))
            if ln.line_no is not None:
                line_nos.append(str(ln.line_no))
            pd_ = ln.promised_date
            if pd_ is not None and (promised is None or pd_ < promised):
                promised = pd_
        merged_bom_id = bom_id_key or None

        product_key = f"{product_code_key}#{idx}"

        if merged_bom_id:
            tree_nodes = await _expand_bom_tree(db, merged_bom_id, total_qty)
        else:
            tree_nodes = []

        kit_tree = _attach_kit_to_tree(tree_nodes, mat_by_code, covered_codes)

        # 产品级汇总:按 material_code 去重计数
        per_product_counts: dict[str, KitAnalysisMaterialItem] = {}
        _collect_unique_materials(kit_tree, mat_by_code, per_product_counts)

        leaf_total = len(per_product_counts)
        leaf_received = sum(1 for m in per_product_counts.values() if m.status == "fully_received")
        leaf_partial = sum(1 for m in per_product_counts.values() if m.status == "partial_received")
        leaf_not_ordered = sum(1 for m in per_product_counts.values() if m.status in ("not_ordered", "self_made_unlinked"))
        leaf_overdue = sum(1 for m in per_product_counts.values() if m.status == "overdue")
        leaf_stagnant = sum(1 for m in per_product_counts.values() if m.is_stagnant)
        kit_rate = (leaf_received / leaf_total) if leaf_total else 0.0
        risk = _kit_risk_level(kit_rate)

        products.append(ProductKitSummary(
            line_no=",".join(line_nos) if line_nos else None,
            product_code=first.product_code,
            product_name=first.product_name,
            product_model=getattr(first, "product_model", None),
            bom_no=getattr(first, "bom_no", None),
            bom_id=merged_bom_id,
            order_qty=_to_float(total_qty),
            promised_date=promised,
            leaf_total=leaf_total,
            leaf_received=leaf_received,
            leaf_partial=leaf_partial,
            leaf_not_ordered=leaf_not_ordered,
            leaf_overdue=leaf_overdue,
            leaf_stagnant=leaf_stagnant,
            has_bom=bool(merged_bom_id),
            kit_rate=kit_rate,
            risk_level=risk,
        ))
        bom_trees[product_key] = kit_tree

    # 3) 孤儿物料 = 订单级物料中,material_code 不在任何产品 BOM 树里
    orphan_materials = [m for code, m in mat_by_code.items() if code not in covered_codes]

    return OrderProductKitBreakdownOut(
        order_no=order_no,
        products=products,
        orphan_materials=orphan_materials,
        bom_trees=bom_trees,
    ).model_dump()


def _attach_kit_to_tree(
    nodes: list,
    mat_by_code: dict[str, KitAnalysisMaterialItem],
    covered_codes: set[str],
) -> list[BomKitMaterialItem]:
    """把 BomDetailItemOut 节点转成 BomKitMaterialItem,并按 material_code 关联订单级齐套数字。"""
    result: list[BomKitMaterialItem] = []
    for node in nodes:
        code = node.material_code
        kit_item = mat_by_code.get(code) if code else None
        if code:
            covered_codes.add(code)
        base_data = kit_item.model_dump() if kit_item else {}
        base_data.update({
            "level": node.level,
            "bom_id": node.bom_id,
            "standard_qty": node.standard_qty,
            "req_qty": node.req_qty,
            "has_sub_bom": node.has_sub_bom,
            "children": _attach_kit_to_tree(node.children, mat_by_code, covered_codes),
        })
        if not kit_item:
            # BOM 有但 MrpPlanOrder 没记录 → 清掉必填字段的占位
            base_data["material_code"] = code or ""
            base_data["status"] = "not_in_plan"
            base_data.setdefault("status_label", None)
        result.append(BomKitMaterialItem(**base_data))
    return result


def _collect_unique_materials(
    nodes: list,
    mat_by_code: dict[str, KitAnalysisMaterialItem],
    out: dict[str, KitAnalysisMaterialItem],
) -> None:
    """DFS 收集树中所有出现在 mat_by_code 的 material_code(去重)。"""
    for node in nodes:
        code = getattr(node, "material_code", None)
        if code and code in mat_by_code and code not in out:
            out[code] = mat_by_code[code]
        children = getattr(node, "children", []) or []
        if children:
            _collect_unique_materials(children, mat_by_code, out)
```

注意 `_status_for_plan` / `_kit_met_for_plan` 不需要改;我们直接复用 `KitAnalysisMaterialItem.status` 已有的字符串值。

### 验证

```powershell
python -c "import ast; ast.parse(open(r'backend/app/services/material/kit_analysis_service.py', encoding='utf-8').read()); print('syntax ok')"
```

workdir: `D:\wanghuazheng\project\SPC-v2`

预期: `syntax ok`

---

## Task 3: 后端 — 新增端点

**文件**: `backend/app/api/v1/material/kit_analysis.py`

### Step 3.1: 更新导入

把第 10 行的 schema 导入扩展:

```python
from app.schemas.material.schemas import (
    KitAnalysisItem,
    KitAnalysisMaterialItem,
    OrderProductKitBreakdownOut,
)
```

把第 11 行的 service 导入扩展:

```python
from app.services.material.kit_analysis_service import (
    get_kit_analysis,
    get_order_materials,
    get_order_product_breakdown,
)
```

### Step 3.2: 在文件末尾追加新端点

在文件末尾(`order_materials` 端点之后)追加:

```python
@router.get("/{order_no}/product-breakdown", response_model=ResponseModel[OrderProductKitBreakdownOut])
async def order_product_breakdown(
    order_no: str,
    current_user: dict = Depends(PermissionChecker("materials.kit_analysis", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await get_order_product_breakdown(db, order_no=order_no)
    return ResponseModel(data=result)
```

### 验证

启动 uvicorn:

```powershell
uvicorn app.main:app --port 8000
```

workdir: `D:\wanghuazheng\project\SPC-v2\backend`(单独一个 terminal,保持运行)

新 terminal 中调用(替换 `<TOKEN>` 为登录后的 access_token,`<ORDER_NO>` 为系统中真实存在的销售订单号):

```powershell
$hdr = @{ Authorization = "Bearer <TOKEN>" }
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/materials/kit-analysis/<ORDER_NO>/product-breakdown" -Headers $hdr | ConvertTo-Json -Depth 6
```

预期:返回的 JSON 含 `code: 0`、`data.products`、`data.bom_trees`、`data.orphan_materials` 三个字段。

---

## Task 4: 前端 — API 客户端

**文件**: `frontend/src/services/api.ts`

### Step 4.1: 在 `getOrderMaterials` 之后加新方法

找到第 204-205 行(`getOrderMaterials` 定义),在其后插入:

```typescript
  getOrderProductBreakdown: (orderNo: string) =>
    api.get(`/materials/kit-analysis/${orderNo}/product-breakdown`),
```

完整上下文:

```typescript
  getKitAnalysis: (params: Record<string, any>) =>
    api.get('/materials/kit-analysis', { params }),
  getOrderMaterials: (orderNo: string, params: Record<string, any>) =>
    api.get(`/materials/kit-analysis/${orderNo}/materials`, { params }),
  getOrderProductBreakdown: (orderNo: string) =>
    api.get(`/materials/kit-analysis/${orderNo}/product-breakdown`),
```

### 验证

```powershell
npx tsc --noEmit -p frontend
```

workdir: `D:\wanghuazheng\project\SPC-v2`(或直接在最后 `npm run build`)

预期: 无新增报错(若没改其他文件,可能因类型报错来自其他地方;关注新行不引入报错)。

---

## Task 5: 前端 — 类型定义

**文件**: `frontend/src/pages/MaterialCenter/KitAnalysis/index.tsx`

### Step 5.1: 在 `interface KitItem { ... }`(约 43-55 行)之后追加新类型

```typescript
interface BomKitMaterialItem extends MaterialItem {
  level: number
  bom_id: string | null
  standard_qty: number | null
  req_qty: number | null
  has_sub_bom: boolean
  children: BomKitMaterialItem[]
}

interface ProductKitSummary {
  line_no: string | null
  product_code: string | null
  product_name: string | null
  product_model: string | null
  bom_no: string | null
  bom_id: string | null
  order_qty: number | null
  promised_date: string | null
  leaf_total: number
  leaf_received: number
  leaf_partial: number
  leaf_not_ordered: number
  leaf_overdue: number
  leaf_stagnant: number
  has_bom: boolean
  kit_rate: number
  risk_level: string
}

interface OrderProductKitBreakdown {
  order_no: string
  products: ProductKitSummary[]
  orphan_materials: MaterialItem[]
  bom_trees: Record<string, BomKitMaterialItem[]>
}
```

### Step 5.2: 在 `MaterialItem` 接口(约 9-41 行)末尾补一个字段

`MaterialItem` 当前缺 `transit_qty`(后端有,前端没声明)。在 `bom_demand_qty: number | null`(第 40 行)之后追加一行:

```typescript
  transit_qty: number | null
```

并把 `status: string`(第 34 行)允许扩展值,不需改类型 — `string` 已涵盖 `"not_in_plan"`。

### 验证

留到 Task 11 一起 build。

---

## Task 6: 前端 — 创建子组件目录与 ProductList

**文件**: `frontend/src/pages/MaterialCenter/KitAnalysis/components/ProductList.tsx`(新建)

```tsx
import React from 'react'
import { Progress, Tag } from 'antd'
import type { ProductKitSummary } from '../index'

const RISK_COLOR: Record<string, string> = { red: '#e11d48', yellow: '#f59e0b', green: '#16a34a' }
const RISK_LABEL: Record<string, string> = { red: '缺料严重', yellow: '部分齐套', green: '齐套' }

interface Props {
  products: ProductKitSummary[]
  selectedKey: string | null
  onSelect: (key: string) => void
  productKeys: string[]
}

const ProductList: React.FC<Props> = ({ products, selectedKey, onSelect, productKeys }) => {
  return (
    <div style={{ width: 240, flexShrink: 0, borderRight: '1px solid #f0f0f0', paddingRight: 8, overflowY: 'auto' }}>
      <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>产品 ({products.length})</div>
      {products.map((p, idx) => {
        const key = productKeys[idx] ?? `${p.product_code}#${idx}`
        const selected = key === selectedKey
        return (
          <div
            key={key}
            onClick={() => onSelect(key)}
            style={{
              padding: '8px 10px',
              marginBottom: 6,
              borderRadius: 4,
              border: `1px solid ${selected ? '#91d5ff' : '#f0f0f0'}`,
              background: selected ? '#e6f7ff' : '#fff',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 2 }}>
              {p.product_name || p.product_code || '(未命名产品)'}
              {!p.has_bom && <Tag color="default" style={{ marginLeft: 6 }}>无BOM</Tag>}
            </div>
            <div style={{ color: '#888', fontSize: 11 }}>
              {p.product_code} · 订单数 {p.order_qty ?? '-'} · {p.bom_no || '无BOM编号'}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', marginTop: 4 }}>
              <Progress
                percent={Math.round((p.kit_rate || 0) * 100)}
                size="small"
                strokeColor={RISK_COLOR[p.risk_level]}
                style={{ width: 100, marginBottom: 0, marginRight: 8 }}
                showInfo={false}
              />
              <span style={{ color: RISK_COLOR[p.risk_level], fontWeight: 600, fontSize: 12 }}>
                {Math.round((p.kit_rate || 0) * 100)}%
              </span>
              <Tag color={p.risk_level} style={{ marginLeft: 'auto' }}>{RISK_LABEL[p.risk_level]}</Tag>
            </div>
            <div style={{ color: '#888', fontSize: 11, marginTop: 2 }}>
              到齐 {p.leaf_received}/{p.leaf_total}
              {p.leaf_partial > 0 && ` · 部分 ${p.leaf_partial}`}
              {p.leaf_not_ordered > 0 && ` · 未下 ${p.leaf_not_ordered}`}
              {p.leaf_overdue > 0 && ` · 逾期 ${p.leaf_overdue}`}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default ProductList
```

注意:由于 antd Tag 的 `color` prop 接受预设颜色名,而 `red`/`yellow`/`green` 都是 antd 预设,可直接使用。若样式异常,可改成具体十六进制色 via `style`。

### 验证

留到 Task 11。

---

## Task 7: 前端 — 创建 BomMaterialTable

**文件**: `frontend/src/pages/MaterialCenter/KitAnalysis/components/BomMaterialTable.tsx`(新建)

```tsx
import React, { useMemo } from 'react'
import { Table, Tag, Tooltip } from 'antd'
import type { BomKitMaterialItem } from '../index'

const MATERIAL_STATUS_COLOR: Record<string, string> = {
  not_in_plan: 'default',
  not_ordered: 'volcano',
  self_made_unlinked: 'blue',
  partial_received: 'warning',
  fully_received: 'success',
  overdue: 'error',
  pending: 'cyan',
  in_stock: 'green',
}

const fmt = (v: number | null | undefined) => (v == null ? '-' : Number(v).toLocaleString())

interface Props {
  tree: BomKitMaterialItem[]
  loading?: boolean
}

const BomMaterialTable: React.FC<Props> = ({ tree, loading }) => {
  const columns = useMemo(() => [
    {
      title: '层级',
      dataIndex: 'level',
      key: 'level',
      width: 60,
      render: (lv: number) => `L${lv}`,
    },
    {
      title: '物料编码',
      dataIndex: 'material_code',
      key: 'material_code',
      width: 140,
    },
    {
      title: '物料名称',
      dataIndex: 'material_name',
      key: 'material_name',
      width: 160,
      render: (v: string | null) => v || <span style={{ color: '#ccc' }}>-</span>,
    },
    {
      title: '属性',
      dataIndex: 'material_property_label',
      key: 'material_property_label',
      width: 80,
    },
    {
      title: 'BOM 用量',
      dataIndex: 'standard_qty',
      key: 'standard_qty',
      width: 90,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '需求量',
      dataIndex: 'req_qty',
      key: 'req_qty',
      width: 90,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '可用库存',
      dataIndex: 'available_stock_qty',
      key: 'available_stock_qty',
      width: 90,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '在途',
      dataIndex: 'transit_qty',
      key: 'transit_qty',
      width: 80,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '已收',
      dataIndex: 'received_qty',
      key: 'received_qty',
      width: 90,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '短缺',
      dataIndex: 'shortage_qty',
      key: 'shortage_qty',
      width: 90,
      align: 'right' as const,
      render: (v: number | null) =>
        v != null && v > 0 ? <span style={{ color: '#cf1322', fontWeight: 600 }}>{fmt(v)}</span> : fmt(v),
    },
    {
      title: 'ETA',
      dataIndex: 'eta',
      key: 'eta',
      width: 100,
    },
    {
      title: '供应商',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      width: 120,
      render: (v: string | null) => v || <span style={{ color: '#ccc' }}>-</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string, row: BomKitMaterialItem) => {
        if (s === 'not_in_plan') return <Tag>BOM 有 / 计划无</Tag>
        const label = row.status_label || s
        return <Tag color={MATERIAL_STATUS_COLOR[s] || 'default'}>{label}</Tag>
      },
    },
  ], [])

  return (
    <div style={{ flex: 1, minWidth: 0, paddingLeft: 12 }}>
      <div
        style={{
          background: '#e6f7ff',
          border: '1px solid #91d5ff',
          padding: '6px 10px',
          borderRadius: 4,
          fontSize: 12,
          color: '#0050b3',
          marginBottom: 8,
        }}
      >
        齐套数字为<b>订单级聚合</b>(来源 MRP/PO/库存),跨产品不累加;BOM 仅作结构展示
      </div>
      <Table<BomKitMaterialItem>
        rowKey={(r) => `${r.bom_id || ''}-${r.line_no || ''}-${r.material_code || ''}-${r.level}`}
        dataSource={tree}
        columns={columns}
        size="small"
        pagination={false}
        loading={loading}
        scroll={{ x: 1300, y: 360 }}
        expandable={{ childrenColumnName: 'children' }}
      />
    </div>
  )
}

export default BomMaterialTable
```

注意:`line_no` 字段从 `MaterialItem` 继承来,后端 `BomKitMaterialItem` 因继承 `KitAnalysisMaterialItem` 也带该字段。`rowKey` 用复合键避免同物料多层级冲突。

### 验证

留到 Task 11。

---

## Task 8: 前端 — 创建 OrphanMaterialAlert

**文件**: `frontend/src/pages/MaterialCenter/KitAnalysis/components/OrphanMaterialAlert.tsx`(新建)

```tsx
import React, { useState } from 'react'
import { Alert, Table, Tag } from 'antd'
import { DownOutlined, UpOutlined } from '@ant-design/icons'
import type { MaterialItem } from '../index'

const MATERIAL_STATUS_COLOR: Record<string, string> = {
  not_ordered: 'volcano',
  self_made_unlinked: 'blue',
  partial_received: 'warning',
  fully_received: 'success',
  overdue: 'error',
  pending: 'cyan',
  in_stock: 'green',
}

const fmt = (v: number | null | undefined) => (v == null ? '-' : Number(v).toLocaleString())

interface Props {
  orphans: MaterialItem[]
}

const OrphanMaterialAlert: React.FC<Props> = ({ orphans }) => {
  const [expanded, setExpanded] = useState(false)
  if (!orphans || orphans.length === 0) return null

  const columns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 140 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180 },
    { title: '属性', dataIndex: 'material_property_label', key: 'material_property_label', width: 80 },
    { title: 'MRP 数量', dataIndex: 'mrp_qty', key: 'mrp_qty', width: 100, align: 'right' as const, render: fmt },
    { title: '下单数量', dataIndex: 'po_qty', key: 'po_qty', width: 100, align: 'right' as const, render: fmt },
    { title: '已收', dataIndex: 'received_qty', key: 'received_qty', width: 100, align: 'right' as const, render: fmt },
    { title: '短缺', dataIndex: 'shortage_qty', key: 'shortage_qty', width: 100, align: 'right' as const, render: fmt },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (s: string, row: MaterialItem) => (
        <Tag color={MATERIAL_STATUS_COLOR[s] || 'default'}>{row.status_label || s}</Tag>
      ),
    },
  ]

  return (
    <div style={{ marginBottom: 8 }}>
      <Alert
        type="warning"
        showIcon
        message={`本订单有 ${orphans.length} 个物料未关联 BOM(MRP 计划有,BOM 未覆盖)`}
        action={
          <a onClick={() => setExpanded(v => !v)}>
            {expanded ? '收起' : '展开查看'} {expanded ? <UpOutlined /> : <DownOutlined />}
          </a>
        }
      />
      {expanded && (
        <Table<MaterialItem>
          rowKey="material_code"
          dataSource={orphans}
          columns={columns}
          size="small"
          pagination={false}
          scroll={{ x: 900, y: 240 }}
          style={{ marginTop: 8 }}
        />
      )}
    </div>
  )
}

export default OrphanMaterialAlert
```

### 验证

留到 Task 11。

---

## Task 9: 前端 — 创建 OrderProductKitPanel 容器

**文件**: `frontend/src/pages/MaterialCenter/KitAnalysis/components/OrderProductKitPanel.tsx`(新建)

```tsx
import React, { useEffect, useState, useCallback } from 'react'
import { Spin, Empty, message } from 'antd'
import { materialApi } from '@/services/api'
import type { OrderProductKitBreakdown } from '../index'
import ProductList from './ProductList'
import BomMaterialTable from './BomMaterialTable'
import OrphanMaterialAlert from './OrphanMaterialAlert'

interface Props {
  orderNo: string
  breakdown: OrderProductKitBreakdown | null
  onLoaded: (data: OrderProductKitBreakdown) => void
}

const OrderProductKitPanel: React.FC<Props> = ({ orderNo, breakdown, onLoaded }) => {
  const [loading, setLoading] = useState(!breakdown)
  const [selectedKey, setSelectedKey] = useState<string | null>(
    breakdown && breakdown.products.length > 0 ? `${breakdown.products[0].product_code}#0` : null,
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.getOrderProductBreakdown(orderNo)
      onLoaded(res.data)
      const firstKey = res.data?.products?.length ? `${res.data.products[0].product_code}#0` : null
      setSelectedKey(firstKey)
    } catch (e: any) {
      message.error(e.message || '加载产品齐套失败')
    } finally {
      setLoading(false)
    }
  }, [orderNo, onLoaded])

  useEffect(() => {
    if (!breakdown) {
      load()
    }
  }, [breakdown, load])

  if (loading) {
    return <div style={{ padding: 24, textAlign: 'center' }}><Spin tip="加载产品齐套..." /></div>
  }

  if (!breakdown) return null

  if (breakdown.products.length === 0 && breakdown.orphan_materials.length === 0) {
    return <Empty description="本订单无产品线与物料数据" style={{ padding: 24 }} />
  }

  const productKeys = breakdown.products.map((p, idx) => `${p.product_code}#${idx}`)
  const selectedIdx = productKeys.indexOf(selectedKey || '')
  const selectedProduct = selectedIdx >= 0 ? breakdown.products[selectedIdx] : null
  const selectedTree = selectedIdx >= 0
    ? (breakdown.bom_trees[productKeys[selectedIdx]] || [])
    : []

  return (
    <div style={{ padding: '8px 12px 16px 36px' }}>
      <OrphanMaterialAlert orphans={breakdown.orphan_materials} />
      {breakdown.products.length === 0 ? (
        <div style={{ color: '#888', fontSize: 13, padding: 12 }}>
          本订单无产品线数据(SaleOrderLine 为空)
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 12 }}>
          <ProductList
            products={breakdown.products}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
            productKeys={productKeys}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            {selectedProduct && (
              <div style={{ marginBottom: 8, fontSize: 13 }}>
                <b>BOM 物料齐套 — {selectedProduct.product_name || selectedProduct.product_code}</b>
                {' '}
                (BOM: {selectedProduct.bom_no || selectedProduct.bom_id || '-'})
                · 订单数 {selectedProduct.order_qty ?? '-'}
              </div>
            )}
            {selectedProduct && !selectedProduct.has_bom ? (
              <Empty description="该产品未关联 BOM,无物料树可展开" style={{ padding: 24 }} />
            ) : (
              <BomMaterialTable tree={selectedTree} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default OrderProductKitPanel
```

注意:`productKeys` 必须和后端 `bom_trees` 的 key 一致(后端用 `${product_code}#${idx}`,前端同样)。

### 验证

留到 Task 11。

---

## Task 10: 前端 — 改写 KitAnalysis 主页展开区

**文件**: `frontend/src/pages/MaterialCenter/KitAnalysis/index.tsx`

### Step 10.1: 加导入

在文件顶部 import 区(约第 1-7 行之后)加:

```tsx
import OrderProductKitPanel from './components/OrderProductKitPanel'
```

### Step 10.2: 加 breakdown 缓存 state

找到现有 state 声明区(`const [expandedKeys, ...]` 等),在合适位置加:

```tsx
const [breakdownCache, setBreakdownCache] = useState<Record<string, OrderProductKitBreakdown | null>>({})
```

(具体放在 `useState` 调用集中的位置,例如 `materialsLoading` state 旁边。)

### Step 10.3: 删除 / 替换 `handleExpand` 中的预加载逻辑

把现有的 `handleExpand` 函数(约 237-242 行):

```tsx
const handleExpand = useCallback(async (expanded: boolean, record: KitItem) => {
  if (expanded && !record.materials) {
    const filters = materialFilters[record.order_no] || DEFAULT_MATERIAL_FILTERS
    await loadMaterials(record.order_no, filters)
  }
}, [loadMaterials, materialFilters])
```

替换为(新展开时无需预加载,Panel 组件自己负责):

```tsx
const handleExpand = useCallback(async (expanded: boolean, record: KitItem) => {
  // 展开时由 OrderProductKitPanel 懒加载,这里无需操作
}, [])
```

### Step 10.4: 替换 `expandedRowRender`

找到 `expandedRowRender: (row: KitItem) => ( ... )`(约 697-768 行),整个 `expandedRowRender` 的内容替换为:

```tsx
expandedRowRender: (row: KitItem) => (
  <OrderProductKitPanel
    orderNo={row.order_no}
    breakdown={breakdownCache[row.order_no] ?? null}
    onLoaded={(data) => setBreakdownCache(prev => ({ ...prev, [row.order_no]: data }))}
  />
),
```

### Step 10.5: 删除 / 留置旧代码

下列内容在新视图下不再被使用,**可以删除**(让 tsc 不报 unused 更干净),但 `noUnusedLocals: false` 下保留也不会编译报错。优先**删除**避免误导:

- `loadMaterials`(约 201-235 行)
- `handleMaterialFilterChange`(约 244-252 行)
- `handleMaterialSortChange`(约 254-262 行)
- `materialFilters` state(查找 `useState<Record<string, ...>>({})`)
- `materialsLoading` state
- `getMaterialColumns`(若存在;grep 该名)
- 顶部导入里只为这些函数服务的图标(若引发 unused,可留)

### Step 10.6: 保留 / 不动的部分

- `KitItem.materials?` 字段(可选,可保留)
- `MATERIAL_COLUMN_KEYS` / `MATERIAL_COLUMN_LABELS` 等列设置 UI — 已不再被新 Panel 使用,可删除或保留(保留不影响)
- 列设置 Popover(原 700-724 行)— 已不在新 expandedRowRender 内,会自然失效

### 验证

```powershell
npm run build
```

workdir: `D:\wanghuazheng\project\SPC-v2\frontend`

预期: `tsc -b` + `vite build` 成功通过;若 tsc 报错,根据报错路径修剩余 unused import。

---

## Task 11: 端到端验证

### Step 11.1: 后端

确保 Task 3 的 uvicorn 还在运行。若没运行,在 backend 目录:

```powershell
uvicorn app.main:app --port 8000
```

### Step 11.2: 前端

```powershell
npm run dev
```

workdir: `D:\wanghuazheng\project\SPC-v2\frontend`

### Step 11.3: 浏览器手测

1. 访问 `http://localhost:3000/kit-analysis`,登录(`admin` / `admin123`)
2. 展开任一订单行:应看到双栏(左产品列表 + 右 BOM 表) + 可选的顶部提示条
3. 点击左栏不同产品 → 右栏表格切换
4. 若有提示条,点"展开查看" → 出现扁平物料表
5. 收起 / 再次展开同一订单 → 不重新请求(缓存生效,Network 面板验证)
6. 切到 `purchaser01` 账号,确认权限边界一致(应同样可见)

### Step 11.4: 用第二个账号验证权限

退出后用 `purchaser01` / `admin123` 登录,重复 Step 11.3,应得到一致结果(`materials.kit_analysis:read` 两个角色都有)。

### Step 11.5: 边界场景

- 选一个 `SaleOrderLine` 为空的订单(若存在)→ 展开后应看到"本订单无产品线数据"+提示条(若有孤儿)
- 选一个所有产品都没 `bom_id` 的订单 → 左栏每个产品卡片有"无BOM"灰 tag,右栏显示 Empty
- 选一个 BOM 巨大(>500 节点)的订单 → 观察响应时间;若 > 3s,记录到风险章节(本次不优化)

---

## 风险与备注

- **后端 `_expand_bom_tree` 的入参**:函数签名是 `(db, root_bom_id: Optional[str], root_demand_factor: Decimal)`。`root_demand_factor` 这里传该产品的合并 `order_qty`。BOM 的 `req_qty` 在子级会按 `factor × standard_qty / parent_bom.base_qty` 递减计算,这和"订单数 × BOM 用量"的语义一致。
- **`material_property_label` 字段**:`KitAnalysisMaterialItem` 在后端会自动填充;BOM-only 节点(MrpPlanOrder 没记录的)不会经过该填充逻辑,所以 `material_property_label` 可能为 `None`。前端表格中显示为空字符串即可。
- **`product_code` 为空的产品**:分组 key 是 `(product_code or "", bom_id or "")`,可能出现 `("#0", "")` 这样的项;前端会显示"(未命名产品)"。可接受。
- **同一物料在多个产品 BOM 中**:`covered_codes` 是订单级全局集合,只要被任一产品 BOM 覆盖就算"已关联",不会进 orphans。但同一物料的齐套数字会在每个产品的 BOM 树里都显示一遍 — 这已在右栏顶部提示条说明。
- **Pydantic v2 forward ref**:`BomKitMaterialItem.model_rebuild()` 必须调用,否则 `children` 的前向引用解析失败。
- **antd Table 树形数据**:`expandable={{ childrenColumnName: 'children' }}` 让 Table 自动按 `children` 字段渲染树。`rowKey` 必须唯一 — 用复合键避免同物料多层级冲突。
- **未实现的优化**:BOM 物料表当前没有列可见性持久化(原页面有 `kit_analysis_material_columns` key);本计划暂不引入,保持新表精简。若后续需要,可在 `BomMaterialTable` 里接入 `useUiPreferencesStore`。
- **commit / push**:本计划不包含 git 提交步骤,按用户后续指示操作。

## 文件改动清单

新增:
- `backend/app/schemas/material/schemas.py`(追加 ~50 行)
- `backend/app/services/material/kit_analysis_service.py`(追加 ~140 行)
- `backend/app/api/v1/material/kit_analysis.py`(追加 ~12 行)
- `frontend/src/services/api.ts`(追加 2 行)
- `frontend/src/pages/MaterialCenter/KitAnalysis/components/OrderProductKitPanel.tsx`(新建)
- `frontend/src/pages/MaterialCenter/KitAnalysis/components/ProductList.tsx`(新建)
- `frontend/src/pages/MaterialCenter/KitAnalysis/components/BomMaterialTable.tsx`(新建)
- `frontend/src/pages/MaterialCenter/KitAnalysis/components/OrphanMaterialAlert.tsx`(新建)

修改:
- `frontend/src/pages/MaterialCenter/KitAnalysis/index.tsx`(替换展开区,删除旧 filter 逻辑)

不动:
- `backend/init_database.py`(无 schema 变更)
- `backend/app/api/v1/__init__.py`(端点挂在现有 router 上)
- `frontend/src/App.tsx` / `frontend/src/layouts/MainLayout.tsx`(路由/菜单/权限不变)
- Alembic migrations(无表结构变更)
