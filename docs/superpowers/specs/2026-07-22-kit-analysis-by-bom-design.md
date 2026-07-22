# 齐套分析 — 按订单下产品 / BOM 视图

**日期**: 2026-07-22
**作者**: brainstorming session
**状态**: 待评审

## 目标

将现有 `/kit-analysis` 页面的展开行从"扁平物料列表"升级为"按订单下产品 + BOM 多级树形"的齐套视图。

用户原话:
> 齐套分析,可以按照订单下产品的视角查看物料的齐套情况,当选中某个订单时可以按bom列出这些物料的齐套情况

## 范围

### In scope

- 重写 `/kit-analysis` 页面订单行的展开区:左栏产品列表 + 右栏 BOM 物料齐套表
- 顶部订单表 / 统计卡 / 筛选条 / 分页 — **保持现状**
- 新增后端端点 `GET /api/v1/materials/kit-analysis/{order_no}/product-breakdown`
- 顶层订单级聚合数字(沿用现有 `get_kit_analysis` 逻辑)— **不动**
- 删除前端展开行的扁平物料表(完全替换)

### Out of scope

- 跨订单库存分配算法的调整(沿用 `_allocate_stock`)
- `kpi_summary_service.py` 中 kit 占位字段接入真实数据(虽然相关,但是另一项工作)
- `OrderDetail` 页面的"齐套分析" tab(本次不修改,后续可统一)
- 列可见性 / 导出 / AI 工具(`search_kit_analysis`)

## 数据来源策略(关键决策)

**订单级聚合,产品仅看 BOM 结构。**

- 齐套数字(PO 量、已收量、可用库存、短缺、状态等)来自 `MrpPlanOrder` + `PurchaseOrder` + `Inventory`,**只到 `(order_no, material_code)` 粒度**,不带产品维度
- BOM 多级结构来自 `BomDetail`,通过 `SaleOrderLine.bom_id` 关联
- 当同一物料在订单内多个产品的 BOM 中出现时,**每个产品下都显示该物料的订单级聚合数字**(不做按比例拆分)。在 BOM 物料表行上注明"数字为订单级"
- 未在 `MrpPlanOrder` 中但出现在 BOM 的物料:只展示 BOM 用量 × 订单数 作为"需求量",其余字段为 `None`

## 用户流程

```
┌─────────────────────────────────────────────────────────────────────┐
│ 顶部:统计卡 + 筛选条 (保持现状)                                       │
├─────────────────────────────────────────────────────────────────────┤
│ 订单表 (现有 KitAnalysis 表格 + 分页)                                 │
│  ▶ SO-2026-001 · 客户A · 3产品 · 45% · 🔴                            │
│  ▼ SO-2026-002 · 客户B · 1产品 · 80% · 🟡                            │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ ⚠️ 本订单有 2 个物料未关联 BOM  [展开查看]            (可选)     │ │
│  ├──────────────┬─────────────────────────────────────────────────┤ │
│  │ 左栏:产品列表  │ 右栏:选中产品的 BOM 物料齐套表                    │ │
│  │ ● P-1001 主板 │ BOM 物料齐套 — P-1001 主板组件 (BOM-P1001-v2)     │ │
│  │   齐套 45% 🔴 │ 订单数 500 · 单位需求=BOM 用量×订单数              │ │
│  │ ○ P-1002 显示 │ L0 P-1001 主板组件   需500  可用200  短300 🔴    │ │
│  │   齐套 100% 🟢│ L1 M-2001 PCB板     需500  可用500  ✅           │ │
│  │ ○ P-1003 外壳 │ L1 M-2002 芯片(子)  需1000 可用600  短400 🔴    │ │
│  │   齐套 40% 🔴 │ L2 └ M-3001 晶圆    需4000 可用2400 短1600 🔴    │ │
│  │              │ ... (沿用全部 KitAnalysisMaterialItem 字段)        │ │
│  └──────────────┴─────────────────────────────────────────────────┘ │
│  ▶ SO-2026-003 ...                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 交互细节

1. 默认所有订单折叠;点击订单行展开/收起
2. 展开时**懒加载**该订单的 `product-breakdown`;已加载的订单在会话内缓存(切换收起/展开不重新请求)
3. 展开区左栏默认选中**第一个产品**(若订单无产品,见边缘情况 1)
4. 切换产品 → 仅切换右栏表格内容(不重新请求)
5. 左栏产品卡片显示:产品名、订单数、BOM 编号、小型齐套率 + 红/黄/绿徽标
6. 右栏 BOM 物料表为**多级缩进树**:`level` 字段决定缩进,父节点可二次折叠子树
7. 右栏表格沿用现有列可见性持久化(`useUiPreferencesStore`,key `kit_analysis_material_columns`)
8. **未关联物料**:展开区顶部出现提示条 `⚠️ 本订单有 N 个物料未关联 BOM [展开查看]`,点击展开一个扁平物料表(直接渲染 `KitAnalysisMaterialItem` 列表)

## 后端设计

### 新增端点

**文件**: `backend/app/api/v1/material/kit_analysis.py`

```
GET /api/v1/materials/kit-analysis/{order_no}/product-breakdown
```

- 权限: `materials.kit_analysis:read`(沿用)
- 查询参数: 无(后续可加 `include_orphan` 等开关)
- 响应: `ResponseModel[OrderProductKitBreakdownOut]`

### 新增 Schema

**文件**: `backend/app/schemas/material/schemas.py`(在 `KitAnalysisItem` 之后追加)

```python
class BomKitMaterialItem(KitAnalysisMaterialItem):
    """BOM 树节点 + 订单级齐套数字。继承 KitAnalysisMaterialItem 全部字段。"""
    level: int = 1                          # BOM 层级,L0=产品本身
    bom_id: Optional[str] = None            # 该节点所属的 BOM
    standard_qty: Optional[float] = None    # 父级 BOM 中的用量
    req_qty: Optional[float] = None         # BOM 用量 × 产品订单数
    has_sub_bom: bool = False
    children: List["BomKitMaterialItem"] = []


class ProductKitSummary(BaseModel):
    """左栏产品卡片的数据。"""
    line_no: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    product_model: Optional[str] = None
    bom_no: Optional[str] = None
    bom_id: Optional[str] = None
    order_qty: Optional[float] = None
    promised_date: Optional[date] = None
    # 产品级聚合(由其 BOM 叶子物料的订单级状态汇总)
    leaf_total: int = 0
    leaf_received: int = 0          # 状态 = fully_received
    leaf_partial: int = 0           # 状态 = partial_received
    leaf_not_ordered: int = 0
    leaf_overdue: int = 0
    leaf_stagnant: int = 0
    kit_rate: float = 0.0
    risk_level: str = "green"       # green / yellow / red


class OrderProductKitBreakdownOut(BaseModel):
    """新端点的响应体。"""
    order_no: str
    products: List[ProductKitSummary] = []
    orphan_materials: List[KitAnalysisMaterialItem] = []
    # 每个 product 的 BOM 树单独存一份,前端按 product_code 索引
    bom_trees: Dict[str, List[BomKitMaterialItem]] = {}
```

注:`bom_trees` 的 key 为 `product_code`(若重复则用 `product_code#line_no`)。

### 新增 Service 函数

**文件**: `backend/app/services/material/kit_analysis_service.py`

```python
async def get_order_product_breakdown(
    db: AsyncSession,
    order_no: str,
) -> dict:
    ...
```

**实现步骤**:

1. **取产品列表**:查 `SaleOrderLine` where `order_no = order_no`,按 `(product_code, bom_id)` 分组,求和 `order_qty`,取最早的 `promised_date`。复用 `order_materials_service.get_order_product_materials` 的分组逻辑(已存在,L178)
2. **取订单级齐套数字**:调用现有 `get_order_materials(db, order_no=order_no, ...所有 filter=None)`,得到 `List[KitAnalysisMaterialItem]`,在内存中按 `material_code` 建 dict
3. **逐产品展开 BOM 树**:复用 `order_materials_service._expand_bom_tree(db, bom_id, demand_factor=order_qty)`。展开后每个节点按 `material_code` 从第 2 步的 dict 中拷贝齐套数字到 `BomKitMaterialItem`;不在 dict 中的物料只填 BOM 字段(`standard_qty`, `req_qty`, `level`),齐套数字留 `None`
4. **产品级聚合**:对每个产品,深度遍历其 BOM 树叶子节点,按 `status` 字段统计 `leaf_*` 计数;`kit_rate = leaf_received / leaf_total`;`risk_level` 规则与现有 `get_kit_analysis` 一致(≥100% green / ≥80% yellow / 其余 red)
5. **未关联物料**:第 2 步 dict 中所有 `material_code` 减去所有产品 BOM 树遍历到的 `material_code` 集合,剩下的就是孤儿,直接作为 `orphan_materials` 输出
6. 返回 `OrderProductKitBreakdownOut` 的 dict

**性能考量**:单订单的 BOM 深度 ≤ 20、节点数通常 < 几百;`_expand_bom_tree` 已有缓存与环检测。一次性返回完整数据避免前端多次请求。

## 前端设计

### 文件改造

| 文件 | 改造 |
|------|------|
| `frontend/src/services/api.ts` | 在 `materialApi` 加 `getOrderProductBreakdown(orderNo)` 调用新端点 |
| `frontend/src/pages/MaterialCenter/KitAnalysis/index.tsx` | 替换展开区渲染逻辑;新增 `expandedOrderCache` state |
| `frontend/src/pages/MaterialCenter/KitAnalysis/components/OrderProductKitPanel.tsx` | **新建**:展开区容器组件(双栏 + 提示条) |
| `frontend/src/pages/MaterialCenter/KitAnalysis/components/ProductList.tsx` | **新建**:左栏产品列表 |
| `frontend/src/pages/MaterialCenter/KitAnalysis/components/BomMaterialTable.tsx` | **新建**:右栏 BOM 物料树表 |
| `frontend/src/pages/MaterialCenter/KitAnalysis/components/OrphanMaterialAlert.tsx` | **新建**:未关联物料提示条 + 可展开扁平表 |

### 组件 Props(简化)

```typescript
// 顶层 index.tsx
const [expandedOrderNo, setExpandedOrderNo] = useState<string | null>(null);
const [breakdownCache, setBreakdownCache] = useState<Record<string, OrderProductKitBreakdown>>({});

// 展开行 render
(expanded) => expanded ? (
  <OrderProductKitPanel
    orderNo={expandedOrderNo}
    breakdown={breakdownCache[expandedOrderNo]}
    onLoaded={(data) => setBreakdownCache(prev => ({...prev, [expandedOrderNo]: data}))}
  />
) : null

// OrderProductKitPanel
props: { orderNo, breakdown, onLoaded }
内部 state: selectedProductCode, showOrphan
// 展开时若 breakdown 为空,触发 onLoaded(API 调用)

// ProductList
props: { products, selected, onSelect }

// BomMaterialTable
props: { bomTree, columnPrefs }   // 沿用 kit_analysis_material_columns 持久化
内部:多级缩进(antd Table 的 childrenColumnName 或自定义 render)

// OrphanMaterialAlert
props: { orphans }
```

### antd Table 多级 BOM 树渲染

两种实现可选(实现时择一,不在本设计强制):
- **A**:数据自带 `children` 字段,用 antd Table 的 `childrenColumnName="children"` 自动渲染树形展开
- **B**:扁平化 `level` 字段,在 `render` 内用 `paddingLeft: level * 20` 缩进

推荐 **A**(antd 原生支持,交互体验更好)。

## 边缘情况

1. **订单无产品(`SaleOrderLine` 为空)**:展开区显示提示"本订单无产品线数据",直接展示 `orphan_materials` 全部物料
2. **`SaleOrderLine.bom_id` 为 null**:该产品项不能展开 BOM;在产品卡片上加灰色徽标"无 BOM";其订单级物料全归入 `orphan_materials`
3. **BOM 引用的 `bom_id` 在 `scm_bom` 表中不存在**:同上,产品卡片标"无 BOM"
4. **BOM 中物料在 `scm_material` 表中无主数据**:`material_name` 等留空,`material_code` 显示 BOM 上的 ID
5. **BOM 循环引用**:`_expand_bom_tree` 已有 `visited` 集合保护,会截断
6. **物料在 BOM 多个层级出现**:每个层级节点都展示同样的订单级齐套数字(符合"订单级聚合"策略)
7. **同一 `material_code` 在订单级有多个 `MrpPlanOrder` 行(不同 `bill_type`)**:`get_order_materials` 已按 `material_code` 聚合,沿用其结果

## 不动的东西

- `init_database.py`:无新列、无新表 → 不需要改
- Alembic:不涉及
- `MainLayout.tsx` 菜单 / `App.tsx` 路由 / 权限:都复用 `materials.kit_analysis`
- 顶层 `get_kit_analysis` 与订单表统计卡:完全不动

## 验收

实现完成后:

1. 启动 `uvicorn app.main:app --reload --port 8000`,访问 `GET /api/v1/materials/kit-analysis/{order_no}/product-breakdown` 看响应结构
2. 启动前端 `npm run dev`,登录后访问 `/kit-analysis`,展开任一订单:
   - 左栏出现产品列表,每个产品有齐套率/状态
   - 右栏出现 BOM 多级树,每行带齐套数字
   - 切换产品右栏切换
   - 有未关联物料时提示条出现,点击可展开
3. `npm run build`(tsc -b && vite build)— 必须通过(唯一 typecheck)
4. 用 `admin` / `purchaser01` 两个账号分别访问,确认权限边界一致

## 风险

- **BOM 展开性能**:个别订单若 BOM 巨大(>1000 节点),单端点响应可能 > 2s。本次不引入分页/懒加载,若实测慢可在 `BomMaterialTable` 内做产品级懒加载(切换产品时再请求该产品的树)
- **订单级聚合的"双显"困惑**:用户看到同一物料在多个产品下显示相同短缺数字,可能误以为重复。**对策**:在右栏表格头部加固定提示"齐套数字为订单级聚合,跨产品不累加"
