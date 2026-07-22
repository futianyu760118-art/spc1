# 订单详情多级 BOM 展开 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把订单详情页产品列表的 BOM 子件查询从单层改为多级递归展开，返回树形结构并支持前端折叠展示。

**Architecture:** 后端在 `order_materials_service.get_order_product_materials` 中实现 BFS 逐层展开（复用 `kit_analysis_service._get_bom_demand_map` 的成熟模式：每层三步查询——`BomDetail`→`Material`→`Bom`）；schema `BomDetailItemOut` 新增 `level`/`bom_id`/`parent_material_id`/`has_sub_bom`/`children` 字段；前端内层 AntD Table 切换为树模式（`childrenColumnName="children"`）。

**Tech Stack:** Python 3.12 + SQLAlchemy async (asyncpg) + Pydantic v2；React + TypeScript + Ant Design 5。

## Global Constraints

- 严禁 `bom_id` Integer/String 混用——service 层统一 `str()` 强转（与现有 `order_materials_service.py:180` 一致）。
- 严禁手动 `db.commit()`（`get_db()` 自动管理事务）。
- 响应必须用 `ResponseModel` 包裹（前端拦截器要求 `code === 0`）。
- 不修改 `init_database.py`、Alembic、模型列、权限、ERP sync。
- `MAX_LEVEL = 20` 软保护；`visited_bom_ids` 防环；`base_qty` 缺省取 `Decimal("1")`。
- TypeScript 严格模式；`npm run build` 是唯一 typecheck。

---

## Task 1: 扩展 `BomDetailItemOut` schema

**File:** `backend/app/schemas/order/schemas.py` (L341-361)

**Why:** 树形响应需要嵌套字段；向后兼容（老消费者忽略新字段即可）。

**Edit:** 在 `BomDetailItemOut` 末尾追加字段（`from typing import Optional, List` 已在 `schemas.py:3` 导入）。

```python

class BomDetailItemOut(BaseModel):
    material_id: Optional[str] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    spec_model: Optional[str] = None
    unit: Optional[str] = None
    material_type: Optional[str] = None
    line_no: Optional[str] = None
    standard_qty: Optional[float] = None
    aux_qty: Optional[float] = None
    config_type: Optional[str] = None
    lead_offset_days: Optional[int] = None
    back_flush: Optional[int] = None
    scrap_rate: Optional[float] = None
    oper_sn: Optional[str] = None
    process_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    valid_date: Optional[date] = None
    invalid_date: Optional[date] = None
    kit_flag: Optional[int] = None
    req_qty: Optional[float] = None
    # ↓ 新增字段
    level: int = 1
    bom_id: Optional[str] = None
    parent_material_id: Optional[int] = None
    has_sub_bom: bool = False
    children: List["BomDetailItemOut"] = []
```

**Verify:** `BomDetailItemOut.model_rebuild()` 不会报循环引用错误（Pydantic v2 用字符串前向引用即可）。运行：

```bash
cd backend && python -c "from app.schemas.order.schemas import BomDetailItemOut; print(BomDetailItemOut.model_fields.keys())"
```

应看到 `dict_keys([... 'level', 'bom_id', 'parent_material_id', 'has_sub_bom', 'children'])`。

---

## Task 2: 后端实现 BFS 多级展开

**File:** `backend/app/services/order/order_materials_service.py`

**Why:** 替换单层查询为多级 BFS；算法对齐 `kit_analysis_service._get_bom_demand_map`。

### 2a. 在文件顶部加常量

在 `STATUS_LABELS` 字典之后（约 L41 后）追加：

```python
MAX_BOM_LEVEL = 20
```

### 2b. 重写 `get_order_product_materials()`（L149-205）

完整替换为：

```python
async def get_order_product_materials(
    db: AsyncSession,
    order_no: str,
    line_no: Optional[str] = None,
) -> list[OrderProductMaterialsOut]:
    line_query = select(SaleOrderLine).where(SaleOrderLine.order_no == order_no)
    if line_no:
        line_query = line_query.where(SaleOrderLine.line_no == line_no)
    line_result = await db.execute(line_query.order_by(SaleOrderLine.id))
    lines = line_result.scalars().all()

    if not lines:
        order_query = select(SaleOrder).where(SaleOrder.order_no == order_no)
        if line_no:
            order_query = order_query.where(SaleOrder.line_no == line_no)
        order = (await db.execute(order_query)).scalar_one_or_none()
        if order:
            lines = [
                SimpleNamespace(
                    order_no=order.order_no,
                    line_no=order.line_no,
                    product_code=order.product_code,
                    product_name=order.product_name,
                    product_model=None,
                    order_qty=order.order_qty,
                    promised_date=order.promised_date,
                    bom_id=None,
                )
            ]

    result: list[OrderProductMaterialsOut] = []
    for line in lines:
        line_bom_id = str(line.bom_id) if getattr(line, "bom_id", None) else None
        order_qty_decimal = Decimal(str(line.order_qty)) if line.order_qty is not None else Decimal("0")
        tree = await _expand_bom_tree(db, line_bom_id, order_qty_decimal)
        result.append(_build_line_materials(line, tree))
    return result
```

### 2c. 新增 `_expand_bom_tree()` 辅助函数（紧跟 `get_order_product_materials` 之后）

这是 BFS 主体。**关键设计点**：父子挂载 (`parent.children.append(child)`) 必须在**整个 BFS 跑完后**统一执行，否则子节点还未创建就尝试挂载会失败。

```python
async def _expand_bom_tree(
    db: AsyncSession,
    root_bom_id: Optional[str],
    root_demand_factor: Decimal,
) -> list[BomDetailItemOut]:
    """BFS 展开多层 BOM，返回顶层节点列表（children 已递归挂载）。

    每层三步查询：
      1) BomDetail WHERE bom_id IN (本层)
      2) Material  WHERE erp_material_id IN (新子件)  [增量缓存]
      3) Bom       WHERE material_id IN (本层子件)    [回查主表，判断是否继续展开]

    算法对齐 kit_analysis_service._get_bom_demand_map：
      - visited_bom_ids 防环
      - 子级 factor = 父级 factor × standard_qty / parent_bom.base_qty
      - base_qty 缺省取 1
      - 父子挂载延迟到 BFS 结束后统一执行
    """
    if not root_bom_id:
        return []

    master_by_mid: dict[int, Material] = {}
    # 节点缓存：key = (bom_id, line_no) → BomDetailItemOut
    node_by_key: dict[tuple[str, str], BomDetailItemOut] = {}
    # 父子关系列表：(parent_key, child_key) —— BFS 结束后统一挂载
    parent_links: list[tuple[tuple[str, str], tuple[str, str]]] = []
    top_keys: list[tuple[str, str]] = []
    visited: set[str] = set()

    # queue: (bom_id, factor, parent_material_id, parent_key_or_None, level)
    queue: list[tuple[str, Decimal, Optional[int], Optional[tuple[str, str]], int]] = [
        (root_bom_id, root_demand_factor, None, None, 1)
    ]

    while queue:
        # 仅处理本层未访问过的 bom_id（防环 + 深度上限）
        level_bom_ids = {
            item[0] for item in queue
            if item[0] not in visited and item[4] <= MAX_BOM_LEVEL
        }
        if not level_bom_ids:
            break
        visited.update(level_bom_ids)

        # 步骤 1：本层 BomDetail
        detail_result = await db.execute(
            select(BomDetail)
            .where(BomDetail.bom_id.in_(level_bom_ids))
            .order_by(BomDetail.bom_id, BomDetail.line_no)
        )
        details_by_bom: dict[str, list[BomDetail]] = {}
        for d in detail_result.scalars().all():
            details_by_bom.setdefault(d.bom_id, []).append(d)

        # 步骤 2：补物料主数据（增量）
        new_mids = {
            d.material_id for details in details_by_bom.values()
            for d in details if d.material_id
        } - master_by_mid.keys()
        if new_mids:
            mat_result = await db.execute(
                select(Material).where(Material.erp_material_id.in_(new_mids))
            )
            for m in mat_result.scalars().all():
                master_by_mid[m.erp_material_id] = m

        # 步骤 3：回查 bom 主表 —— 哪些子件本身有 BOM
        child_mids = {
            d.material_id for details in details_by_bom.values()
            for d in details if d.material_id
        }
        sub_bom_by_mid: dict[int, Bom] = {}
        if child_mids:
            bom_result = await db.execute(
                select(Bom).where(Bom.material_id.in_(child_mids))
            )
            for b in bom_result.scalars().all():
                # 同 material_id 多条时取第一条（与 _get_bom_demand_map 一致）
                if b.material_id not in sub_bom_by_mid:
                    sub_bom_by_mid[b.material_id] = b

        # 组装节点 + 入队下级
        next_queue: list[tuple[str, Decimal, Optional[int], Optional[tuple[str, str]], int]] = []
        for bom_id, factor, parent_mid, parent_key, level in queue:
            if bom_id not in level_bom_ids:
                continue  # 本层已跳过（环 或 上一轮已处理）
            for d in details_by_bom.get(bom_id, []):
                master = master_by_mid.get(d.material_id) if d.material_id else None
                if d.standard_qty is not None and factor is not None:
                    req_qty_decimal: Optional[Decimal] = d.standard_qty * factor
                else:
                    req_qty_decimal = d.standard_qty

                sub_bom = sub_bom_by_mid.get(d.material_id) if d.material_id else None
                key = (bom_id, d.line_no or "")
                node_by_key[key] = BomDetailItemOut(
                    material_id=str(d.material_id) if d.material_id is not None else None,
                    material_code=master.material_code if master else None,
                    material_name=master.material_name if master else None,
                    spec_model=master.spec_model if master else None,
                    unit=master.unit_of_measure if master else None,
                    material_type=d.material_type or (master.material_type if master else None),
                    line_no=d.line_no,
                    standard_qty=_to_float(d.standard_qty),
                    aux_qty=_to_float(d.aux_qty),
                    config_type=d.config_type,
                    lead_offset_days=d.lead_offset_days,
                    back_flush=d.back_flush,
                    scrap_rate=_to_float(d.scrap_rate),
                    oper_sn=d.oper_sn,
                    process_id=d.process_id,
                    warehouse_id=d.warehouse_id,
                    valid_date=d.valid_date,
                    invalid_date=d.invalid_date,
                    kit_flag=d.kit_flag,
                    req_qty=_to_float(req_qty_decimal),
                    level=level,
                    bom_id=d.bom_id,
                    parent_material_id=parent_mid,
                    has_sub_bom=sub_bom is not None,
                    children=[],
                )
                if parent_key is None:
                    top_keys.append(key)
                else:
                    parent_links.append((parent_key, key))

                # 子件有 BOM 且未访问过 → 入队下一层
                if sub_bom and sub_bom.bom_id not in visited:
                    base_qty = sub_bom.base_qty if sub_bom.base_qty else Decimal("1")
                    next_factor = (req_qty_decimal or Decimal("0")) / base_qty
                    next_queue.append((
                        sub_bom.bom_id,
                        next_factor,
                        d.material_id,
                        key,
                        level + 1,
                    ))

        queue = next_queue

    # BFS 结束后统一挂载 children（此时所有节点已创建）
    for parent_key, child_key in parent_links:
        parent_node = node_by_key.get(parent_key)
        if parent_node is not None and child_key in node_by_key:
            parent_node.children.append(node_by_key[child_key])

    return [node_by_key[k] for k in top_keys]
```

**已知边界（接受）**：菱形依赖（同一子 BOM 被多个父件引用）只会挂在首次访问的父节点下，与 `kit_analysis_service` 的去重行为一致。如需在多个父件下都展示，需改为按路径复制节点——本期不做。

**Verify:**

```bash
cd backend && python -c "
import asyncio
from app.core.database import get_db
from app.services.order.order_materials_service import _expand_bom_tree, MAX_BOM_LEVEL
print('imports OK, MAX_BOM_LEVEL =', MAX_BOM_LEVEL)
"
```

应输出 `imports OK, MAX_BOM_LEVEL = 20`，无 ImportError / 语法错误。

### 2d. 简化 `_build_line_materials()`（L208-259）

旧函数已无作用（树组装移到 `_expand_bom_tree`）。替换为：

```python
def _build_line_materials(
    line: SaleOrderLine,
    materials: list[BomDetailItemOut],
) -> OrderProductMaterialsOut:
    return OrderProductMaterialsOut(
        line_no=line.line_no,
        product_code=line.product_code,
        product_name=line.product_name,
        product_model=getattr(line, "product_model", None),
        bom_no=getattr(line, "bom_no", None),
        order_qty=_to_float(line.order_qty),
        promised_date=line.promised_date,
        total_materials=len(materials),
        materials=materials,
    )
```

**Verify:**

```bash
cd backend && python -c "
from app.services.order.order_materials_service import _expand_bom_tree, _build_line_materials, MAX_BOM_LEVEL
print('imports OK, MAX_BOM_LEVEL =', MAX_BOM_LEVEL)
"
```

应输出 `imports OK, MAX_BOM_LEVEL = 20`，无 ImportError。

---

## Task 3: 启动后端、调用接口验证

**Why:** 无单测；按 AGENTS.md 约定靠真实请求验证。

**Steps:**

1. 启动后端：`cd backend && uvicorn app.main:app --reload --port 8000`
2. 登录拿 token：`POST /api/v1/basicdata/auth/login`，body `login_type=employee&username=admin&password=admin123`（form-urlencoded）。
3. 找一个含多层 BOM 的订单号（可查 DB：`SELECT line.order_no, line.bom_id, d.material_id, b.bom_id AS sub_bom_id FROM sale_order_line line JOIN scm_bom_detail d ON d.bom_id = line.bom_id::text LEFT JOIN scm_bom b ON b.material_id = d.material_id WHERE b.bom_id IS NOT NULL LIMIT 5;`）。
4. 调用 `GET /api/v1/orders/{order_no}/product-materials`（带 `Authorization: Bearer <token>`）。
5. 检查响应 `data[0].materials[i].children` 是否存在并嵌套；同一物料的 `req_qty` 应与齐套分析 tab 的 `bom_demand_qty` 数量级一致。

**预期：** 顶层 `materials` 数组里 `has_sub_bom=true` 的节点，其 `children` 非空且 `level=2`；可能继续嵌套 `level=3`。

---

## Task 4: 扩展前端 `BomDetailItem` 类型

**File:** `frontend/src/pages/OrderDelivery/OrderDetail/index.tsx` (L39-60)

**Edit:** 在 `BomDetailItem` 接口末尾追加字段：

```ts
interface BomDetailItem {
  material_id: string | null
  material_code: string | null
  material_name: string | null
  spec_model: string | null
  unit: string | null
  material_type: string | null
  line_no: string | null
  standard_qty: number | null
  aux_qty: number | null
  config_type: string | null
  lead_offset_days: number | null
  back_flush: number | null
  scrap_rate: number | null
  oper_sn: string | null
  process_id: string | null
  warehouse_id: string | null
  valid_date: string | null
  invalid_date: string | null
  kit_flag: number | null
  req_qty: number | null
  // ↓ 新增
  level?: number
  bom_id?: string | null
  parent_material_id?: number | null
  has_sub_bom?: boolean
  children?: BomDetailItem[]
}
```

**Verify:** 文件保存后无 TS 报错（IDE 实时检查）。正式校验放在 Task 6 的 `npm run build`。

---

## Task 5: 前端内层 Table 切树模式 + 子件图标

**File:** `frontend/src/pages/OrderDelivery/OrderDetail/index.tsx`

### 5a. 修改 `getBomDetailColumns`（L402-422）

在"物料编码"列加图标渲染，提示 `has_sub_bom`。把第 404 行改为：

```ts
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 150,
      render: (v: string | null, r: BomDetailItem) => (
        <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
          {v || '-'}
          {r.has_sub_bom && (
            <Tag color="blue" style={{ marginLeft: 6, fontSize: 11 }}>组件</Tag>
          )}
        </span>
      )
    },
```

需在文件顶部确认 `Tag` 已从 `antd` 导入（实测 `index.tsx:3` 已包含 `Tag`，无需改动）。

### 5b. 修改内层 Table（L735-743）

切换为树模式，并把 `rowKey` 改成复合 key（避免 index-based 在树模式下导致展开状态错乱）：

```tsx
                          <Table
                            columns={getBomDetailColumns()}
                            dataSource={row.materials || []}
                            rowKey={(r: BomDetailItem) =>
                              `${r.bom_id || ''}|${r.line_no || ''}|${r.material_id || ''}|${r.level || 1}`
                            }
                            size="small"
                            pagination={false}
                            scroll={{ x: 1700 }}
                            locale={{ emptyText: '暂无BOM明细' }}
                            expandable={{
                              childrenColumnName: 'children',
                              defaultExpandAllRows: false,
                            }}
                          />
```

**说明：** AntD Table 的 `childrenColumnName: 'children'` 会自动给有非空 `children` 的行加展开箭头并按层级缩进；`rowKey` 用复合字符串确保跨层唯一。

**Verify:** 保存后浏览器刷新订单详情页，子件表格的"组件"行出现箭头，点击可展开下层物料。

---

## Task 6: 前端 typecheck

**Why:** AGENTS.md 明确 `npm run build` 是唯一 typecheck。

```bash
cd frontend && npm run build
```

**预期：** `tsc -b && vite build` 全部通过，无 TS 错误。若报 `Tag` 未定义等，按提示补 import。

---

## Task 7: 端到端联调验证

**Why:** 确认前后端联通、树形展示正确、用量折算无误。

**检查清单：**

- [ ] 订单详情页产品 tab 打开后，有子 BOM 的子件行显示"组件"标签 + 展开箭头。
- [ ] 点击箭头展开，下层物料正确出现，数量为父件需求量 × 子件 standard_qty / 父 BOM base_qty。
- [ ] 多层 BOM 可递归展开（≥3 层）。
- [ ] 同订单切到"齐套分析" tab，对比同一底层物料的 `bom_demand_qty`，与本页多层展开累计的需求量在数量级上一致。
- [ ] 无子 BOM 的子件（`has_sub_bom=false`）不出现箭头，行为同改动前。
- [ ] 无 BOM 的订单（`bom_id` 为空）仍正常显示空 BOM 表，不报错。

---

## Done Criteria

1. 后端 `BomDetailItemOut` 含 `level`/`bom_id`/`parent_material_id`/`has_sub_bom`/`children` 五个新字段。
2. `get_order_product_materials` 返回多层嵌套树，`req_qty` 按 `base_qty` 正确折算。
3. 前端订单详情页内层 Table 显示为可折叠树，组件件有"组件"标签。
4. `npm run build` 通过。
5. 不影响其他 tab（齐套分析、采购等）。
