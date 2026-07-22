# BOM 物料齐套表列排序与筛选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为齐套分析中「产品的物料齐套表」(BomMaterialTable) 的 13 列添加排序与筛选能力,数据由后端打平返回,前端在扁平表上完成排序/筛选。

**Architecture:** 后端新增 `GET /product-bom-flat?product_code=X` 返回扁平 BOM 节点数组(DFS 拍平)。前端 `BomMaterialTable` 从树形表改为扁平表,使用 Ant Design `Table` 的 `sorter` 与 `filters` / `filterDropdown` 在每列添加交互;`OrderProductKitPanel` 在产品切换时调新接口拉扁平数据。

**Tech Stack:** FastAPI + SQLAlchemy (async, asyncpg), Pydantic; React + TypeScript + Ant Design 5 + Day.js。

**Spec:** `docs/superpowers/specs/2026-07-22-bom-kit-table-sort-filter-design.md`

---

## Global Constraints

- Python 3.12, Node 20
- 后端响应必须包 `ResponseModel` 信封 `{code, message, data}`(`app/schemas/common.py`)
- 前端 typecheck 仅 `npm run build`(无 lint/test)
- 后端新增列/字段同时改 SQLAlchemy 模型 与 `init_database.py.migrate_columns`(本次不改 schema,只新增 endpoint,故不涉及)
- 不引入新依赖
- 沿用权限 `materials.kit_analysis` 的 `read` 动作
- 既有 `GET /product-breakdown` 接口不修改

---

## Task 1: 后端 Schema 新增 BomKitFlatItem / BomKitFlatResponse

**Files:**
- Edit: `backend/app/schemas/material/schemas.py`

**Step 1.1:** 在第 300 行 `BomKitMaterialItem` 类定义之后(第 301 行 `children: List[...] = []` 之后,`BomKitMaterialItem.model_rebuild()` 之前),新增:

```python
class BomKitFlatItem(KitAnalysisMaterialItem):
    """BOM 节点扁平结构。继承 KitAnalysisMaterialItem 全部字段,新增层级与父引用。"""
    level: int = 1
    bom_id: Optional[str] = None
    standard_qty: Optional[float] = None
    req_qty: Optional[float] = None
    has_sub_bom: bool = False
    parent_bom_id: Optional[str] = None


class BomKitFlatResponse(BaseModel):
    """product-bom-flat 端点的响应体。"""
    order_no: str
    product_code: str
    bom_id: Optional[str] = None
    items: List[BomKitFlatItem] = []
```

**Step 1.2:** 不要新增 `model_rebuild()` —— `BomKitFlatItem` 没有自引用。

**Verification:**
- `cd backend && python -c "from app.schemas.material.schemas import BomKitFlatItem, BomKitFlatResponse; print(BomKitFlatResponse.model_fields['items'].annotation)"` 应打印 `typing.List[app.schemas.material.schemas.BomKitFlatItem]`(或类似)且退出码 0。

---

## Task 2: 后端 Service 新增 _flatten_kit_tree + get_order_product_bom_flat

**Files:**
- Edit: `backend/app/services/material/kit_analysis_service.py`

**Step 2.1:** 在第 1-39 行的 import 块中,把 schema import 改为:

```python
from app.schemas.material.schemas import (
    BomKitFlatItem,
    BomKitFlatResponse,
    BomKitMaterialItem,
    KitAnalysisItem,
    KitAnalysisMaterialItem,
    OrderProductKitBreakdownOut,
    ProductKitSummary,
)
```

**Step 2.2:** 在文件末尾(第 1141 行 `def _collect_unique_materials` 之后,或紧跟 `_attach_kit_to_tree`)追加两个新函数:

```python
def _flatten_kit_tree(
    nodes: list[BomKitMaterialItem],
    parent_bom_id: Optional[str],
) -> list[BomKitFlatItem]:
    """DFS 拍平 BOM 树,每行 BomKitFlatItem.parent_bom_id = 父节点 bom_id。"""
    result: list[BomKitFlatItem] = []
    for node in nodes:
        flat = BomKitFlatItem(
            **{k: v for k, v in node.model_dump().items() if k != "children"},
            parent_bom_id=parent_bom_id,
        )
        result.append(flat)
        if node.children:
            result.extend(_flatten_kit_tree(node.children, node.bom_id))
    return result


async def get_order_product_bom_flat(
    db: AsyncSession,
    order_no: str,
    product_code: str,
) -> dict:
    """返回指定产品在指定订单下的 BOM 全节点扁平数组。

    实现:复用 get_order_product_breakdown 的 mat_by_code 关联与 _attach_kit_to_tree 树构建,
    然后对该产品的 bom_tree 做 DFS 拍平。
    """
    breakdown = await get_order_product_breakdown(db, order_no=order_no)
    target_product = next(
        (p for p in breakdown["products"] if p["product_code"] == product_code),
        None,
    )
    if not target_product:
        return BomKitFlatResponse(
            order_no=order_no, product_code=product_code, bom_id=None, items=[]
        ).model_dump()

    product_idx = breakdown["products"].index(target_product)
    product_key = f"{target_product['product_code'] or ''}#{product_idx}"
    bom_id = target_product.get("bom_id")
    tree_nodes = breakdown["bom_trees"].get(product_key, [])
    flat_items = _flatten_kit_tree(tree_nodes, parent_bom_id=None)

    return BomKitFlatResponse(
        order_no=order_no,
        product_code=product_code,
        bom_id=bom_id,
        items=flat_items,
    ).model_dump()
```

**Verification:**
- `cd backend && python -c "from app.services.material.kit_analysis_service import _flatten_kit_tree, get_order_product_bom_flat; print('ok')"` 退出码 0。

---

## Task 3: 后端 API 路由新增 /product-bom-flat

**Files:**
- Edit: `backend/app/api/v1/material/kit_analysis.py`

**Step 3.1:** 在 import 块(schema 导入,line 10-14)改为:

```python
from app.schemas.material.schemas import (
    BomKitFlatResponse,
    KitAnalysisItem,
    KitAnalysisMaterialItem,
    OrderProductKitBreakdownOut,
)
```

**Step 3.2:** 在 service import 块(line 15-19)改为:

```python
from app.services.material.kit_analysis_service import (
    get_kit_analysis,
    get_order_materials,
    get_order_product_bom_flat,
    get_order_product_breakdown,
)
```

**Step 3.3:** 在文件末尾(第 103 行 `return ResponseModel(data=result)` 之后)追加:

```python
@router.get(
    "/{order_no}/product-bom-flat",
    response_model=ResponseModel[BomKitFlatResponse],
)
async def order_product_bom_flat(
    order_no: str,
    product_code: str = Query(..., description="产品代码,精确匹配"),
    current_user: dict = Depends(PermissionChecker("materials.kit_analysis", "read")),
    db: AsyncSession = Depends(get_db),
):
    result = await get_order_product_bom_flat(
        db, order_no=order_no, product_code=product_code
    )
    return ResponseModel(data=result)
```

**Verification:**
- `cd backend && python -c "from app.api.v1.material.kit_analysis import router; print([r.path for r in router.routes if 'product-bom-flat' in r.path])"` 应打印包含 `'/materials/kit-analysis/{order_no}/product-bom-flat'`(或类似)的列表,退出码 0。

---

## Task 4: 前端 TS 类型新增 BomKitFlatItem / BomKitFlatResponse

**Files:**
- Edit: `frontend/src/pages/MaterialCenter/KitAnalysis/index.tsx`

**Step 4.1:** 在第 66 行 `BomKitMaterialItem` 接口结尾 `}` 之后(第 67 行空行前)插入:

```ts
export interface BomKitFlatItem extends Omit<BomKitMaterialItem, 'children'> {
  parent_bom_id: string | null
}

export interface BomKitFlatResponse {
  order_no: string
  product_code: string
  bom_id: string | null
  items: BomKitFlatItem[]
}
```

**Verification:**
- `cd frontend && npx tsc -b --noEmit` 退出码 0(等价于 build 前的 typecheck)。

---

## Task 5: 前端 API client 新增 getOrderProductBomFlat

**Files:**
- Edit: `frontend/src/services/api.ts`

**Step 5.1:** 在第 206-207 行(齐套分析 API client 区块)之后追加:

```ts
  getOrderProductBomFlat: (orderNo: string, productCode: string) =>
    api.get(`/materials/kit-analysis/${orderNo}/product-bom-flat`, {
      params: { product_code: productCode },
    }),
```

**Verification:** `cd frontend && npx tsc -b --noEmit` 退出码 0。

---

## Task 6: 前端 BomMaterialTable 重构为扁平表 + 全列排序筛选

**Files:**
- Replace: `frontend/src/pages/MaterialCenter/KitAnalysis/components/BomMaterialTable.tsx`

整文件替换为以下内容(完整版,直接 `write` 整个文件):

```tsx
import React, { useMemo, useState } from 'react'
import { Table, Tag, InputNumber, DatePicker, Space, Button } from 'antd'
import type { ColumnType, TablePaginationConfig } from 'antd/es/table'
import type { FilterConfirmProps } from 'antd/es/table/interface'
import dayjs from 'dayjs'
import type { BomKitFlatItem } from '../index'

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

const fmt = (v: number | null | undefined) =>
  v == null ? '-' : Number(v).toLocaleString()

const NumberRangeFilter: React.FC<{
  dataIndex: string
  onConfirm: (min?: number, max?: number) => void
  onReset: () => void
  confirm: (param?: FilterConfirmProps) => void
}> = ({ onConfirm, onReset, confirm }) => {
  const [min, setMin] = useState<number | null>(null)
  const [max, setMax] = useState<number | null>(null)
  return (
    <div style={{ padding: 8, width: 220 }} onClick={(e) => e.stopPropagation()}>
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <InputNumber
          placeholder="最小值"
          value={min}
          onChange={(v) => setMin(v as number | null)}
          style={{ width: '100%' }}
        />
        <InputNumber
          placeholder="最大值"
          value={max}
          onChange={(v) => setMax(v as number | null)}
          style={{ width: '100%' }}
        />
        <Space>
          <Button
            type="primary"
            size="small"
            onClick={() => {
              onConfirm(min ?? undefined, max ?? undefined)
              confirm()
            }}
          >
            确定
          </Button>
          <Button
            size="small"
            onClick={() => {
              setMin(null)
              setMax(null)
              onReset()
              confirm()
            }}
          >
            重置
          </Button>
        </Space>
      </Space>
    </div>
  )
}

const DateRangeFilter: React.FC<{
  onConfirm: (start?: string, end?: string) => void
  onReset: () => void
  confirm: (param?: FilterConfirmProps) => void
}> = ({ onConfirm, onReset, confirm }) => {
  const [range, setRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)
  return (
    <div style={{ padding: 8, width: 260 }} onClick={(e) => e.stopPropagation()}>
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <DatePicker.RangePicker
          value={range as any}
          onChange={(v) => setRange(v as any)}
          style={{ width: '100%' }}
        />
        <Space>
          <Button
            type="primary"
            size="small"
            onClick={() => {
              const start = range?.[0]?.format('YYYY-MM-DD')
              const end = range?.[1]?.format('YYYY-MM-DD')
              onConfirm(start, end)
              confirm()
            }}
          >
            确定
          </Button>
          <Button
            size="small"
            onClick={() => {
              setRange(null)
              onReset()
              confirm()
            }}
          >
            重置
          </Button>
        </Space>
      </Space>
    </div>
  )
}

interface Props {
  items: BomKitFlatItem[]
  loading?: boolean
}

const BomMaterialTable: React.FC<Props> = ({ items, loading }) => {
  const [filters, setFilters] = useState<Record<string, (string | number | null)[]>>({})
  const [sortInfo, setSortInfo] = useState<{ columnKey?: string; order?: 'ascend' | 'descend' }>({})

  // 文本列 filters 集合
  const textFilterOptions = useMemo(() => {
    const build = (key: keyof BomKitFlatItem) => {
      const set = new Set<string>()
      items.forEach((it) => {
        const v = it[key]
        if (v != null && v !== '') set.add(String(v))
      })
      return Array.from(set)
        .sort((a, b) => a.localeCompare(b))
        .map((v) => ({ text: v, value: v }))
    }
    return {
      material_code: build('material_code'),
      material_name: build('material_name'),
      material_property_label: build('material_property_label'),
      supplier_name: build('supplier_name'),
      status: build('status'),
    }
  }, [items])

  const columns = useMemo<ColumnType<BomKitFlatItem>[]>(() => {
    const numRange = (dataIndex: keyof BomKitFlatItem): ColumnType<BomKitFlatItem> => {
      const key = String(dataIndex)
      return {
        title: '',
        dataIndex: key as any,
        key,
        sorter: (a, b) => {
          const av = (a as any)[dataIndex] ?? -Infinity
          const bv = (b as any)[dataIndex] ?? -Infinity
          return Number(av) - Number(bv)
        },
        filteredValue: filters[key] as any,
        filterDropdown: (props) => (
          <NumberRangeFilter
            dataIndex={key}
            confirm={props.confirm}
            onConfirm={(min, max) =>
              setFilters((prev) => ({ ...prev, [key]: [min ?? null, max ?? null] }))
            }
            onReset={() =>
              setFilters((prev) => {
                const cp = { ...prev }
                delete cp[key]
                return cp
              })
            }
          />
        ),
        render: fmt,
      }
    }

    const textCol = (
      title: string,
      dataIndex: keyof BomKitFlatItem,
      width: number,
      optsKey: keyof typeof textFilterOptions,
    ): ColumnType<BomKitFlatItem> => ({
      title,
      dataIndex: dataIndex as any,
      key: String(dataIndex),
      width,
      sorter: (a, b) =>
        String((a as any)[dataIndex] ?? '').localeCompare(String((b as any)[dataIndex] ?? '')),
      filters: textFilterOptions[optsKey],
      filteredValue: filters[String(dataIndex)] as any,
      filterSearch: true,
      onFilter: (value, record) => String((record as any)[dataIndex] ?? '') === String(value),
      render: (v: any) => (v == null || v === '' ? <span style={{ color: '#ccc' }}>-</span> : v),
    })

    return [
      {
        title: '层级',
        dataIndex: 'level',
        key: 'level',
        width: 60,
        sorter: (a, b) => (a.level ?? 0) - (b.level ?? 0),
        render: (lv: number) => `L${lv}`,
      },
      textCol('物料编码', 'material_code', 140, 'material_code'),
      textCol('物料名称', 'material_name', 160, 'material_name'),
      textCol('属性', 'material_property_label', 80, 'material_property_label'),
      { ...numRange('standard_qty'), title: 'BOM 用量', width: 90, align: 'right' as const },
      { ...numRange('req_qty'), title: '需求量', width: 90, align: 'right' as const },
      { ...numRange('stock_qty'), title: '即时库存', width: 90, align: 'right' as const },
      { ...numRange('transit_qty'), title: '在途', width: 80, align: 'right' as const },
      { ...numRange('received_qty'), title: '已收', width: 90, align: 'right' as const },
      {
        ...numRange('shortage_qty'),
        title: '短缺',
        width: 90,
        align: 'right' as const,
        render: (v: number | null) =>
          v != null && v > 0 ? (
            <span style={{ color: '#cf1322', fontWeight: 600 }}>{fmt(v)}</span>
          ) : (
            fmt(v)
          ),
      },
      {
        title: 'ETA',
        dataIndex: 'eta',
        key: 'eta',
        width: 100,
        sorter: (a, b) => String(a.eta ?? '').localeCompare(String(b.eta ?? '')),
        filteredValue: filters['eta'] as any,
        filterDropdown: (props) => (
          <DateRangeFilter
            confirm={props.confirm}
            onConfirm={(start, end) =>
              setFilters((prev) => ({ ...prev, eta: [start ?? null, end ?? null] }))
            }
            onReset={() =>
              setFilters((prev) => {
                const cp = { ...prev }
                delete cp.eta
                return cp
              })
            }
          />
        ),
        render: (v: string | null) => (v ? v : <span style={{ color: '#ccc' }}>-</span>),
      },
      textCol('供应商', 'supplier_name', 120, 'supplier_name'),
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        sorter: (a, b) => String(a.status ?? '').localeCompare(String(b.status ?? '')),
        filters: textFilterOptions.status,
        filteredValue: filters['status'] as any,
        filterSearch: true,
        onFilter: (value, record) => record.status === String(value),
        render: (s: string, row: BomKitFlatItem) => {
          if (s === 'not_in_plan') return <Tag>BOM 有 / 计划无</Tag>
          const label = row.status_label || s
          return <Tag color={MATERIAL_STATUS_COLOR[s] || 'default'}>{label}</Tag>
        },
      },
    ] as ColumnType<BomKitFlatItem>[]
  }, [textFilterOptions, filters])

  const dataSource = useMemo(() => {
    // 先过滤
    let arr = items
    Object.entries(filters).forEach(([key, vals]) => {
      if (vals == null) return
      // 数字范围:vals = [min, max]
      if (key === 'standard_qty' || key === 'req_qty' || key === 'stock_qty' ||
          key === 'transit_qty' || key === 'received_qty' || key === 'shortage_qty') {
        const [min, max] = vals as (number | null)[]
        arr = arr.filter((it) => {
          const v = (it as any)[key]
          if (v == null) return min == null && max == null ? true : false
          if (min != null && Number(v) < Number(min)) return false
          if (max != null && Number(v) > Number(max)) return false
          return true
        })
        return
      }
      if (key === 'eta') {
        const [start, end] = vals as (string | null)[]
        arr = arr.filter((it) => {
          if (!it.eta) return false
          if (start && it.eta < start) return false
          if (end && it.eta > end) return false
          return true
        })
        return
      }
      // 文本 / 状态:in 集合
      if (Array.isArray(vals) && vals.length > 0) {
        const set = new Set(vals.map(String))
        arr = arr.filter((it) => set.has(String((it as any)[key] ?? '')))
      } else if (Array.isArray(vals) && vals.length === 0) {
        // 重置后为空数组 → 不过滤
      }
    })
    // 再排序
    if (sortInfo.columnKey && sortInfo.order) {
      const k = sortInfo.columnKey
      const dir = sortInfo.order === 'ascend' ? 1 : -1
      arr = [...arr].sort((a, b) => {
        const av = (a as any)[k]
        const bv = (b as any)[k]
        if (av == null && bv == null) return 0
        if (av == null) return -1 * dir
        if (bv == null) return 1 * dir
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
        return String(av).localeCompare(String(bv)) * dir
      })
    }
    return arr
  }, [items, filters, sortInfo])

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
      <Table<BomKitFlatItem>
        rowKey={(r) =>
          `${r.bom_id || ''}-${r.material_code || ''}-${r.level}-${r.parent_bom_id || ''}-${r.status || ''}`
        }
        dataSource={dataSource}
        columns={columns}
        size="small"
        pagination={false}
        loading={loading}
        scroll={{ x: 1300, y: 360 }}
        onChange={(pagination: TablePaginationConfig, _filters, sorter: any) => {
          setSortInfo({ columnKey: sorter?.columnKey, order: sorter?.order })
        }}
      />
    </div>
  )
}

export default BomMaterialTable
```

**Verification:**
- `cd frontend && npx tsc -b --noEmit` 退出码 0。
- 视觉检查(后续手动测试):列头出现排序箭头和漏斗图标。

---

## Task 7: 前端 OrderProductKitPanel 适配扁平数据

**Files:**
- Edit: `frontend/src/pages/MaterialCenter/KitAnalysis/components/OrderProductKitPanel.tsx`

**Step 7.1:** 整文件替换为以下内容:

```tsx
import React, { useEffect, useState, useCallback } from 'react'
import { Spin, Empty, message } from 'antd'
import { materialApi } from '@/services/api'
import type { BomKitFlatItem, OrderProductKitBreakdown } from '../index'
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
  const [bomFlat, setBomFlat] = useState<BomKitFlatItem[]>([])
  const [bomFlatLoading, setBomFlatLoading] = useState(false)

  const loadBreakdown = useCallback(async () => {
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
      loadBreakdown()
    }
  }, [breakdown, loadBreakdown])

  const selectedProduct =
    breakdown && selectedKey
      ? breakdown.products.find(
          (p) => `${p.product_code || ''}#${breakdown.products.indexOf(p)}` === selectedKey,
        ) || null
      : null

  useEffect(() => {
    if (!breakdown || !selectedProduct || !selectedProduct.has_bom) {
      setBomFlat([])
      return
    }
    let cancelled = false
    setBomFlatLoading(true)
    materialApi
      .getOrderProductBomFlat(orderNo, selectedProduct.product_code || '')
      .then((res: any) => {
        if (!cancelled) {
          setBomFlat(res.data?.items || [])
        }
      })
      .catch((e: any) => {
        if (!cancelled) message.error(e.message || '加载 BOM 物料失败')
      })
      .finally(() => {
        if (!cancelled) setBomFlatLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [breakdown, selectedProduct, orderNo])

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin tip="加载产品齐套..." />
      </div>
    )
  }

  if (!breakdown) return null

  if (breakdown.products.length === 0 && breakdown.orphan_materials.length === 0) {
    return <Empty description="本订单无产品线与物料数据" style={{ padding: 24 }} />
  }

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
            ) : bomFlatLoading && bomFlat.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center' }}>
                <Spin tip="加载 BOM..." />
              </div>
            ) : (
              <BomMaterialTable items={bomFlat} loading={bomFlatLoading} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default OrderProductKitPanel
```

**Verification:**
- `cd frontend && npx tsc -b --noEmit` 退出码 0。

---

## Task 8: 检查 ProductList 是否需要调整

**Files:**
- Read-only check: `frontend/src/pages/MaterialCenter/KitAnalysis/components/ProductList.tsx`

**Step 8.1:** 读 `ProductList.tsx` 第 1-30 行,确认它的 props 是否仍然有 `productKeys`(我在 Task 7 中已移除)。如果它仍要求 `productKeys`,需要从调用处删除该 prop。

打开文件,确认:

```ts
interface Props {
  products: ProductKitSummary[]
  selectedKey: string | null
  onSelect: (key: string) => void
  productKeys?: string[]  // 可能存在
}
```

如果 `productKeys` 是 required,执行 Step 8.2;如果 optional 或不存在,跳过。

**Step 8.2 (条件性):** 如果 ProductList 必须传 productKeys,在 Task 7 的 `<ProductList ... />` 调用处补充:

```tsx
const productKeys = (breakdown?.products || []).map(
  (p) => `${p.product_code || ''}#${(breakdown?.products || []).indexOf(p)}`,
)
// ...
<ProductList
  products={breakdown.products}
  selectedKey={selectedKey}
  onSelect={setSelectedKey}
  productKeys={productKeys}
/>
```

**Verification:** `cd frontend && npx tsc -b --noEmit` 退出码 0。

---

## Task 9: 完整 typecheck 与构建验证

**Step 9.1:** 后端:
```bash
cd backend
python -c "from app.schemas.material.schemas import BomKitFlatItem, BomKitFlatResponse; \
from app.services.material.kit_analysis_service import _flatten_kit_tree, get_order_product_bom_flat; \
from app.api.v1.material.kit_analysis import router; \
print([r.path for r in router.routes if hasattr(r, 'path')])"
```
期望输出包含 `'/materials/kit-analysis/{order_no}/product-bom-flat'`,退出码 0。

**Step 9.2:** 前端 typecheck + build:
```bash
cd frontend
npm run build
```
期望退出码 0,`dist/` 生成,`tsc -b` 0 错误。

---

## Task 10: 手动验证(开发环境)

**Step 10.1:** 启动后端:
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Step 10.2:** 登录拿 token:
```bash
TOK=$(curl -s -X POST http://localhost:8000/api/v1/basicdata/auth/login \
  -d 'login_type=employee&username=admin&password=admin123' | jq -r '.data.access_token')
```

**Step 10.3:** 选一个有 BOM 的订单测试扁平接口(把 `HJ-xxx` / `HJ-001` 替换成真实编号):
```bash
curl -H "Authorization: Bearer $TOK" \
  'http://localhost:8000/api/v1/materials/kit-analysis/HJ-xxx/product-bom-flat?product_code=HJ-001' | jq
```
期望 `code:0`,`data.items` 是非空数组,每项含 `level`、`bom_id`、`material_code`、`parent_bom_id`。

**Step 10.4:** 前端启 dev server:
```bash
cd frontend
npm run dev
```

**Step 10.5:** 浏览器手测:
1. 登录 admin / admin123
2. 进入「物料齐套中心 → 齐套分析」
3. 展开一个有 BOM 的订单,选中第一个产品
4. BOM 表加载完成后:
   - 点每列列头的排序箭头,正/逆序生效
   - 点每列列头的漏斗图标:
     - 物料编码/名称/属性/供应商 → 多选下拉(可搜索)
     - BOM用量/需求量/即时库存/在途/已收/短缺 → 双 InputNumber 范围
     - ETA → 日期范围选择
     - 状态 → 状态码多选
   - 任一筛选确认后,列表过滤生效;「重置」清掉
5. 切换产品 → 排序/筛选状态清空,新数据加载
6. 切换到无 BOM 产品 → 显示 `Empty` 占位

---

## Rollback

如需回滚:
1. `git revert <commit>` 或分别回退 6 个文件的改动
2. 不影响既有 `/product-breakdown` 接口(`BomMaterialTable` 移除会导致 `OrderProductKitPanel` 编译失败,需一起回退)