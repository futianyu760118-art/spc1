# BOM 物料齐套表 — 列排序与筛选

日期: 2026-07-22
范围: 物料齐套中心 → 齐套分析 → 展开订单 → 选中产品后展示的「BOM 物料齐套表」

## 1. 背景与现状

### 1.1 目标表
- 文件: `frontend/src/pages/MaterialCenter/KitAnalysis/components/BomMaterialTable.tsx`
- 形态: 树形 `Table`,`defaultExpandAllRows: true`、`showExpandColumn: false`
- 13 列: 层级 / 物料编码 / 物料名称 / 属性 / BOM用量 / 需求量 / 即时库存 / 在途 / 已收 / 短缺 / ETA / 供应商 / 状态
- 现状: **无任何排序与筛选**,列定义在 `useMemo([])` 内,仅是静态展示
- 数据源: `selectedTree`(由 `OrderProductKitPanel` 传入,内容 = `breakdown.bom_trees[productKey]`)

### 1.2 关联代码
- 页面容器: `frontend/src/pages/MaterialCenter/KitAnalysis/components/OrderProductKitPanel.tsx`
- 页面入口: `frontend/src/pages/MaterialCenter/KitAnalysis/index.tsx`
- API client: `frontend/src/services/api.ts`(`materialApi`,201-207 行)
- 后端路由: `backend/app/api/v1/material/kit_analysis.py`
- 后端服务: `backend/app/services/material/kit_analysis_service.py`(`get_order_product_breakdown`、`_attach_kit_to_tree`)
- Schema: `backend/app/schemas/material/schemas.py`(`BomKitMaterialItem`、`OrderProductKitBreakdownOut`)
- 数据类型(前端): `frontend/src/pages/MaterialCenter/KitAnalysis/index.tsx:59`(`BomKitMaterialItem`)

## 2. 设计目标

1. BOM 物料齐套表每一列都支持排序与筛选
2. 排序、筛选在浏览器前端完成(无后端往返)
3. 表退化为扁平表(数据由后端打平返回),不再使用 `expandable` 树形结构
4. 既有 `/product-breakdown` 接口保持不变(向后兼容)

## 3. 设计方案

### 3.1 后端:新增扁平接口

新增一个 `GET /api/v1/materials/kit-analysis/{order_no}/product-bom-flat?product_code=X` 接口,响应为该产品的 BOM 全节点扁平数组。

#### 3.1.1 Schema 新增(`backend/app/schemas/material/schemas.py`)

```python
class BomKitFlatItem(KitAnalysisMaterialItem):
    """扁平 BOM 节点。继承 KitAnalysisMaterialItem 全部字段,新增层级与父引用。"""
    level: int = 1
    bom_id: Optional[str] = None
    standard_qty: Optional[float] = None
    req_qty: Optional[float] = None
    has_sub_bom: bool = False
    parent_bom_id: Optional[str] = None  # 直系父节点 bom_id


class BomKitFlatResponse(BaseModel):
    """product-bom-flat 端点的响应。"""
    order_no: str
    product_code: str
    bom_id: Optional[str] = None
    items: List[BomKitFlatItem] = []
```

> 说明: `BomKitFlatItem` 复用 `KitAnalysisMaterialItem` 字段;`children` 字段不暴露。

#### 3.1.2 Service 新增(`backend/app/services/material/kit_analysis_service.py`)

```python
async def get_order_product_bom_flat(
    db: AsyncSession,
    order_no: str,
    product_code: str,
) -> dict:
    """返回指定产品在指定订单下的 BOM 全节点扁平数组。

    逻辑:
      1) 调 get_order_product_breakdown 拿到完整 breakdown
      2) 找到 product_code 对应的 product_key 与 bom_id
      3) 用 _attach_kit_to_tree 同样的 mat_by_code 关联订单级齐套数字
      4) 递归 _flatten_kit_tree 把树打平,每个节点带 parent_bom_id
    """
```

新增私有递归辅助:

```python
def _flatten_kit_tree(
    nodes: list[BomKitMaterialItem],
    parent_bom_id: Optional[str],
) -> list[BomKitFlatItem]:
    """DFS 拍平 BOM 树,每行 BomKitFlatItem.parent_bom_id = 父节点 bom_id。"""
```

`_attach_kit_to_tree` 不修改,通过在其输出后做 DFS 拍平获得扁平数组(避免修改既有树构建逻辑,降低回归风险)。

#### 3.1.3 API 新增(`backend/app/api/v1/material/kit_analysis.py`)

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
    result = await get_order_product_bom_flat(db, order_no=order_no, product_code=product_code)
    return ResponseModel(data=result)
```

权限沿用 `materials.kit_analysis` 的 `read` 动作。

### 3.2 前端:API client 新增

`frontend/src/services/api.ts`(`materialApi` 区块,201-207 行附近)新增:

```ts
getOrderProductBomFlat: (orderNo: string, productCode: string) =>
  api.get(`/materials/kit-analysis/${orderNo}/product-bom-flat`, { params: { product_code: productCode } }),
```

类型补全:`frontend/src/pages/MaterialCenter/KitAnalysis/index.tsx:59` 之后新增:

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

### 3.3 前端:BomMaterialTable 改为扁平表 + 全列排序/筛选

`BomMaterialTable.tsx` 改造点:

1. **数据形态变更**
   - props 由 `tree: BomKitMaterialItem[]` 改为 `items: BomKitFlatItem[]`
   - 移除 `expandable`(扁平表无需展开)
   - `rowKey` 使用 `${bom_id}-${material_code}-${level}-${parent_bom_id || ''}` 保证唯一

2. **13 列全部添加 sorter**

   | 列 | dataIndex | sorter 类型 | filters 类型 |
   |---|---|---|---|
   | 层级 | level | numeric | — |
   | 物料编码 | material_code | string | `filters`(从 items 去重) |
   | 物料名称 | material_name | string | `filters` |
   | 属性 | material_property_label | string | `filters` |
   | BOM 用量 | standard_qty | numeric | `filterDropdown`(双 InputNumber min/max) |
   | 需求量 | req_qty | numeric | `filterDropdown`(双 InputNumber min/max) |
   | 即时库存 | stock_qty | numeric | `filterDropdown`(双 InputNumber min/max) |
   | 在途 | transit_qty | numeric | `filterDropdown`(双 InputNumber min/max) |
   | 已收 | received_qty | numeric | `filterDropdown`(双 InputNumber min/max) |
   | 短缺 | shortage_qty | numeric | `filterDropdown`(双 InputNumber min/max) |
   | ETA | eta | date(`compare` ISO 字符串) | `filterDropdown`(DatePicker.RangePicker) |
   | 供应商 | supplier_name | string | `filters` |
   | 状态 | status | string | `filters`(从 items 去重) |

3. **筛选 / 排序状态**:本组件内 `useState<{ columnKey, order, filters }>`,由 Antd `Table.onChange` 写入;`filteredValue` 通过 `columns[i].filteredValue` 注入,使外部受控。**不持久化到 store**(避免切换产品时状态串味;YAGNI)。

4. **每列 sorter**:
   - numeric 列:`sorter: (a, b) => (a.x ?? -Infinity) - (b.x ?? -Infinity)`,支持 undefined
   - 字符串列:`sorter: (a, b) => String(a.x ?? '').localeCompare(String(b.x ?? ''))`
   - 日期列(ETA):`sorter: (a, b) => String(a.eta ?? '').localeCompare(String(b.eta ?? ''))`(ISO 字符串可直接比)

5. **filterDropdown 复用**:
   - 数字范围:定义本组件内私有组件 `NumberRangeFilter`,接收 `dataIndex` 与 `onConfirm(min, max)`,通过 `column.filterDropdown` 渲染;确认后写入 state 并 `confirm()`
   - 日期范围:同上,组件 `DateRangeFilter`,使用 antd `DatePicker.RangePicker`

6. **filters 列**:用 `useMemo` 在 `columns` 之前根据 `items` 计算各列的 `{text, value}` 数组(去重 + 排序)。

### 3.4 前端:OrderProductKitPanel 适配

`OrderProductKitPanel.tsx` 改动:

1. 新增 state:`const [bomFlat, setBomFlat] = useState<BomKitFlatItem[] | null>(null)`、`const [bomFlatLoading, setBomFlatLoading] = useState(false)`
2. `useEffect` 依赖 `[selectedKey]`:
   - 取 `selectedProduct.product_code`(注意:同一 product_code 可能对应多个 bom_id,以 `breakdown.bom_trees[productKey]` 首个节点的 bom_id 为准;传入 `product_code` 即可,后端按 product_code 匹配)
   - 清空 `bomFlat = null`,`setBomFlatLoading(true)`
   - 调 `materialApi.getOrderProductBomFlat(orderNo, productCode)`
   - `setBomFlat(res.data.items)`, `finally setBomFlatLoading(false)`
3. 把 `<BomMaterialTable tree={selectedTree} />` 替换为 `<BomMaterialTable items={bomFlat || []} loading={bomFlatLoading} />`
4. loading 体验:首次切换产品时,扁平表区域显示 `<Spin tip="加载 BOM..." />`(用 antd `Spin` 包裹),已有 flat 时不闪
5. `breakdown` 仍由 `getOrderProductBreakdown` 提供(产品摘要 + 孤儿物料不变),**两个接口并行调用时机**:
   - 方案 A(推荐):`getOrderProductBreakdown` 仍按原时机(订单展开时);选中产品时再追加 `getOrderProductBomFlat`
   - 实施细节:不合并,保持两个职责清晰的接口

### 3.5 不变 / 不做

- 路由不变,菜单不变,权限不变
- 不改既有 `GET /product-breakdown` 接口
- 不持久化筛选/排序状态到 zustand store
- 不做列宽自定义
- 不做列显示/隐藏切换
- 不做导出 CSV

## 4. 数据流总览

```
用户点击展开订单
  → OrderProductKitPanel.load()
    → materialApi.getOrderProductBreakdown(orderNo)        # 既有,保持不变
    → 渲染产品列表 + 选中第一个产品
  → useEffect([selectedKey])
    → materialApi.getOrderProductBomFlat(orderNo, productCode)   # 新增
    → 渲染 BomMaterialTable(items=扁平数组)

用户切换产品
  → useEffect 重新触发 → 重新打平加载

用户在表内点排序 / 筛选
  → Table.onChange 写入 BomMaterialTable 内部 state
  → filteredValue / sorter 由列定义读取并展示
```

## 5. 验证步骤

1. **后端 typecheck**: `cd backend && python -c "from app.schemas.material.schemas import BomKitFlatItem, BomKitFlatResponse; from app.services.material.kit_analysis_service import get_order_product_bom_flat; from app.api.v1.material.kit_analysis import router"` 无 ImportError
2. **后端手工**: `uvicorn` 启动后,
   - `curl -H "Authorization: Bearer $TOK" 'http://localhost:8000/api/v1/materials/kit-analysis/HJ-xxx/product-bom-flat?product_code=HJ-001'` 返回 `{code:0, data:{items:[...]}}`,每个 item 含 level、parent_bom_id
3. **前端 typecheck**: `cd frontend && npm run build` 必须 0 错误
4. **前端手测**:
   - 进入「物料齐套中心 → 齐套分析」
   - 展开一个订单,选中一个产品
   - BOM 表加载后:
     - 点每列列头的排序图标,正序/逆序生效
     - 点每列列头的漏斗图标,弹筛选层,确认后列表过滤生效
     - 数字范围 / 日期范围 / 文本包含 / 状态多选 均生效
   - 切换到另一个产品 → 排序与筛选状态清空(产品级隔离)
   - 切换到无 BOM 的产品 → 显示 `Empty`("该产品未关联 BOM")

## 6. 风险与回滚

- 风险: 后端 `_flatten_kit_tree` 与 `_attach_kit_to_tree` 走两遍遍历,产品 BOM 深时可能有额外开销。BOM 深度通常 ≤ 4 层,节点数 ≤ 200,可接受。
- 回滚: 移除 `product-bom-flat` 端点 + 回退 `BomMaterialTable` 到原 `tree` props + 回退 `OrderProductKitPanel` 即可,既有 `/product-breakdown` 完全不动。