# 订单详情多级 BOM 展开设计

- **日期**: 2026-07-21
- **范围**: 订单详情页（`/orders/:orderNo`）"产品列表"tab 的 BOM 子件展示
- **目标**: 把当前单层 BOM 查询改成多级递归展开——子件若自身在 `scm_bom` 中有 BOM 记录，继续下钻其 `scm_bom_detail`，形成树形结构返回并展示

## 1. 背景

订单详情页通过 `GET /api/v1/orders/{order_no}/product-materials` 获取每款产品的 BOM 子件清单。

- **当前实现** (`backend/app/services/order/order_materials_service.py:149-205`)：仅做一次 `SELECT BomDetail WHERE bom_id IN (line.bom_id)`，纯单层，无视子件本身是否还有 BOM。
- **现成可复用模式**：`backend/app/services/material/kit_analysis_service.py:302-412` 的 `_get_bom_demand_map()` 已实现完整的 BFS 多级展开（齐套分析 tab 在用），含防环、按 `base_qty` 折算用量。本设计直接套用其算法骨架。

## 2. 数据模型回顾

```
SaleOrderLine.bom_id (Integer)  ──cast(str)──►  Bom.bom_id (String, unique)
                                                Bom.material_id (Integer) ──┐
                                                                           │
BomDetail.bom_id (String)  ────── joins ────── Bom.bom_id                   │
BomDetail.material_id (Integer) ───── 回查 ────► Bom.material_id (Integer) ─┘
```

- 链接键：`BomDetail.material_id` (Integer) → `Bom.material_id` (Integer)。命中即代表该子件自身有 BOM，需用其 `Bom.bom_id` 再查 `BomDetail`。
- **类型陷阱**：`SaleOrderLine.bom_id` 是 `Integer`，`Bom.bom_id`/`BomDetail.bom_id` 是 `String(64)`。service 层统一 `str()` 强转（与现有 `order_materials_service.py:180` 一致）。
- 无 ORM `relationship()`，全部手工 dict 组装。

## 3. 后端改动

### 3.1 `BomDetailItemOut` 扩展（`backend/app/schemas/order/schemas.py`）

新增 4 个字段（其余字段全部保留，向后兼容）：

```python
class BomDetailItemOut(BaseModel):
    # ... 现有字段保持不变 ...
    level: int = 1                                # 层级：1 = 产品直属子件
    bom_id: Optional[str] = None                  # 该子件所属 BOM 的 bom_id（来自 BomDetail.bom_id）
    parent_material_id: Optional[int] = None      # 父件 material_id（根层为 None）
    has_sub_bom: bool = False                     # 该子件自身是否还有 BOM（前端图标提示）
    children: List["BomDetailItemOut"] = []       # 多级子件
```

顶层 `OrderProductMaterialsOut.materials` 类型不变，仍为 `List[BomDetailItemOut]`，只是元素现在可嵌套。

### 3.2 `get_order_product_materials()` 改造（`order_materials_service.py`）

用 BFS 替换当前的单层查询。算法（按产品 line 维度展开，因为不同 line 的 `order_qty`/折算系数不同）：

```
visited: set[str]                         # 已处理的 bom_id，防环
queue: [(bom_id, parent_req_factor, parent_material_id, level)]
  初始: (str(line.bom_id), line.order_qty, None, 1)

while queue 非空 and level <= MAX_LEVEL(20):
    level_bom_ids = {bid for bid,* in queue if bid not in visited}
    if not level_bom_ids: break
    visited |= level_bom_ids

    # 步骤 1：取本层子件
    details = SELECT BomDetail WHERE bom_id IN (level_bom_ids) ORDER BY bom_id, line_no

    # 步骤 2：补本层新出现子件的物料主数据（增量缓存到全局 master_by_mid）
    new_mids = {d.material_id for d in details} - master_by_mid.keys()
    if new_mids:
        materials = SELECT Material WHERE erp_material_id IN (new_mids)
        # 合入 master_by_mid

    # 步骤 3：回查 bom 主表——哪些子件本身有 BOM
    child_mids = {d.material_id for d in details if d.material_id}
    sub_boms = SELECT Bom WHERE material_id IN (child_mids)
    sub_bom_by_mid: dict[int, Bom] = {b.material_id: b for b in sub_boms}

    # 组装本层节点 + 计算下级入队
    for (bom_id, factor, parent_mid, level) in queue:
        for d in details_for(bom_id):
            master = master_by_mid.get(d.material_id)
            # 子件需求量 = 父级 factor × 子件 standard_qty
            req_qty = d.standard_qty * factor if both present else d.standard_qty
            sub_bom = sub_bom_by_mid.get(d.material_id)
            node = BomDetailItemOut(
                ... 现有字段 ...,
                level=level,
                bom_id=d.bom_id,
                parent_material_id=parent_mid,
                has_sub_bom=sub_bom is not None,
                req_qty=req_qty,
                children=[],
            )
            # 挂到父节点的 children 列表（根层挂到 line.materials）
            # 入队下级：base_qty 折算为"每单位"用量
            if sub_bom and sub_bom.bom_id not in visited:
                base_qty = sub_bom.base_qty or Decimal("1")
                next_queue.append((
                    sub_bom.bom_id,
                    req_qty / base_qty,         # 下级的 factor
                    d.material_id,              # 下级的 parent_material_id
                    level + 1,
                ))
    queue = next_queue
```

**关键点**：

- **用量折算**与 `_get_bom_demand_map:407-408` 完全一致：父级 `factor × standard_qty / base_qty`。`base_qty` 缺省取 1。
- **`MAX_LEVEL = 20`** 软保护，防脏数据爆栈（正常 BOM 深度 2–4 层）。
- **防环**：`visited_bom_ids` 跟踪，重复 bom_id 跳过；同时入队前再次检查 `not in visited`（与现成模式一致）。
- **每层批量 IN 查询**，循环次数 = BOM 深度，无 N+1。
- **物料主数据全局缓存** `master_by_mid`：跨层累积，避免重复查同物料。
- **保留旧逻辑的兜底分支**：当 `line.bom_id` 为空时，仍返回 `total_materials=0` 的空结果（与现有 SimpleNamespace 分支一致）。

### 3.3 不变的内容

- **API URL、权限、响应外层结构** 完全不变（`GET /orders/{order_no}/product-materials`，`PermissionChecker("orders.list", "read")`，`ResponseModel` 包裹）。
- **不修改** `init_database.py`、Alembic、任何模型列、ERP sync。
- **顶层统计字段**（`total_materials`、`not_ordered_count` 等）仍按现有方式（仅统计顶层直属子件数量，避免和采购/齐套统计口径冲突）。后续若需要全树统计可再加 `total_materials_deep` 字段，本期不做。

## 4. 前端改动（`frontend/src/pages/OrderDelivery/OrderDetail/index.tsx`）

1. **类型扩展** `BomDetailItem` (L39-71)：新增 `level`、`bom_id`、`parent_material_id`、`has_sub_bom`、`children?: BomDetailItem[]`。
2. **内层 Table 切树模式** (L735)：
   ```tsx
   <Table
     dataSource={row.materials}
     columns={getBomDetailColumns()}
     rowKey="material_id"
     expandable={{ childrenColumnName: "children" }}   // 新增：AntD 原生树表
     pagination={false}
     size="small"
   />
   ```
   AntD 会自动给有 `children` 的行加展开箭头并缩进。
3. **物料编码列加图标**：`has_sub_bom` 为 true 时显示一个标识（如 🧩 或 `<Tag color="blue">组件</Tag>`），让用户一眼看出哪些是有下级 BOM 的组件件。
4. **列定义** (`getBomDetailColumns`, L402-422)：可加一列 `level` 显示层级编号（可选，默认不加，避免列变多）。

## 5. 兼容性 & 风险

| 项 | 评估 |
|---|---|
| 老前端 | 顶层结构不变，旧前端忽略 `children` 字段也能用 |
| 性能 | 每层一次批量 IN 查询，深度通常 2–4 层，可接受 |
| 循环 BOM | `visited_bom_ids` + `MAX_LEVEL=20` 双保险 |
| 类型一致性 | service 层统一 `str(bom_id)`，避免 Integer/String 混用 |
| 权限 | 不变，仍是 `orders.list read` |
| ERP sync | 不涉及（只读查询） |

## 6. 验证方法

无测试套件。按 AGENTS.md 约定：

1. `cd backend && npm run build`（前端 typecheck，唯一强校验）。
2. 启动 uvicorn，找一个含多层 BOM 的订单：`GET /api/v1/orders/{order_no}/product-materials`，校验响应里 `materials[i].children` 是否递归嵌套，且 `req_qty` 折算正确。
3. 前端打开订单详情页，确认子件表格出现展开箭头，点击展开下层。
4. 对照齐套分析 tab（已用同样算法）的同一物料需求量，结果应一致。

## 7. 不做的事（YAGNI）

- 不加"是否展开多级"开关——强制改为多级，简化前端。
- 不动权限/分享 token。
- 不动 `init_database.py`/Alembic。
- 不加全树聚合统计字段（`total_materials_deep` 等）。
- 不改其他用到 `BomDetail` 的接口（外购/委外/AI 助手等）。
