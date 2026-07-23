# 委外 BOM 子项齐套状态修正

日期: 2026-07-22
范围: 物料齐套中心 → 齐套分析 → BOM 表中 bill_type=11012(委外申请)的物料行

## 1. 背景与现状

### 1.1 问题
`MrpPlanOrder.bill_type = 11012` 对应「委外申请」物料(委托外协供应商加工/处理的 BOM 子项)。当前 `_get_plan_order_material_items` 在 `kit_analysis_service.py:483` 调用 `_status_for_plan(bill_type, po_summary)`,该函数(line 100-107)把 bill_type=11012 映射到 `material_property=3` 后直接走 `_status()`,而 `_status()` 只读 `PurchaseOrder.received_qty` / `PurchaseOrder.po_qty`。结果:

- 委外物料几乎不会有 PO 行(交给外协厂加工,不需要内部采购下单)
- 这类行被永久打成 `not_ordered`,齐套率永远不计入「已到齐」
- 订单级齐套率被系统性低估

### 1.2 现有数据通路
```python
MrpPlanOrder.sale_order_no  ←→ SubcontractOrderDetail.sale_order_no
MrpPlanOrder.material_code  → Material.material_code
                             ← SubcontractOrderDetail.material_id → Material.erp_material_id
SubcontractOrderDetail.qty, delivery_qty, received_qty, mrp_closed_flag  (明细数量)
SubcontractOrder.voided_flag, closed_flag, status, bill_no               (头)
```

无需新表/新列。

### 1.3 目标
对 bill_type=11012 的 BOM 子项:
- 状态(`status` 字段)从 `SubcontractOrderDetail.received_qty` / `qty` 推导(详见 §3.1)
- BOM 表中显示的「下单量」「已收」也以委外口径填充(用户确认)
- 其他 bill_type(11010 / 11011 / 缺失)路径完全不变

## 2. 范围

| 层 | 文件 | 改动 |
|---|---|---|
| 后端 Service | `backend/app/services/order/order_materials_service.py` | 新增 `MaterialSubSummary` dataclass + `_summarize_subs()` + `_subcontract_status()` |
| 后端 Service | `backend/app/services/material/kit_analysis_service.py` | `_status_for_plan` 接受 `sub_summary` 参数;`_get_plan_order_material_items` 新增一次委外查询并组装 sub_summary;为 bill_type=11012 行替换 status/received_qty/po_qty 显示口径 |

**不变:**
- 前端所有代码(13 列沿用现有渲染)
- Schema / `init_database.py` (不改表结构)
- 路由、菜单、权限
- 既有 `_status()` / PO 路径
- 自定义「完工/在制/未开工」前端展示(YAGNI —— 用既有 status enum 的中文标签)

## 3. 设计细节

### 3.1 `_subcontract_status` 推导规则

`backend/app/services/order/order_materials_service.py`(追加,放在 `_status()` 之后,line 171 附近):

```python
@dataclass
class MaterialSubSummary:
    """按 (sale_order_no, material_code) 聚合的委外订单汇总。和 MaterialPoSummary 平行。"""
    po_no: Optional[str]              # 委外订单 bill_no(逗号分隔多张)
    supplier_name: Optional[str]
    po_qty: Optional[Decimal]         # 委外订单数量(等同订单总量)
    received_qty: Optional[Decimal]   # 已收数量(完工入库)
    first_eta: Optional[date]         # SubcontractOrder.audit_date 作 ETA 兜底
    latest_eta: Optional[date]
    actual_arrival_date: Optional[date]  # 无对应字段,保持 None
    inspection_date: Optional[date]
    po_count: int                     # 委外订单张数
    is_closed: int                    # 任一 header.closed_flag = 1


def _summarize_subs(subs: list) -> list[MaterialSubSummary]:
    # 单 sale_order + material_code 一般汇总成 1 条；多张委外订单按顺序叠
    # 实现类似 _summarize_pos，使用 dict 聚合 by material_code
    ...
    return [MaterialSubSummary(...)]


def _subcontract_status(sub_summary: Optional[MaterialSubSummary]) -> str:
    """委外物料的齐套状态推导。和 _status 对齐 4 出口:已到齐/部分到/待到料/未下单。"""
    if not sub_summary or sub_summary.po_count == 0:
        return "not_ordered"
    received = sub_summary.received_qty
    qty = sub_summary.po_qty
    if received is not None and received > 0:
        if qty is not None and received >= qty:
            return "fully_received"
        return "partial_received"
    # received == 0:没到货；按 audit_date 是否过期 → 不用 overdue(对齐 _status 逻辑)
    return "pending"
```

**为何不输出 overdue / in_stock**:
- `_status()` 的 `overdue` 分支依赖 `po_summary.eta < today`。`SubcontractOrder.audit_date` 不是 ETA,语义不同。
- `_status()` 的 `in_stock` 覆盖发生在更上层的 `_get_plan_order_material_items` 库存满足段(详见 §3.3)。

### 3.2 `_status_for_plan` 增加 sub_summary 形参

`backend/app/services/material/kit_analysis_service.py:100-107`:

```python
def _status_for_plan(
    bill_type: Optional[int],
    po_summary,
    sub_summary = None,           # 新增
) -> str:
    if bill_type == 11012:
        # 委外:不读 po_summary,改读 sub_summary
        return _subcontract_status(sub_summary)
    material_property = BILL_TYPE_TO_MATERIAL_PROPERTY.get(bill_type, 1)
    return _status(material_property, po_summary)
```

### 3.3 `_get_plan_order_material_items` 改动

`backend/app/services/material/kit_analysis_service.py:424-562` 中:

**Step A(新增一次委外查询,line 448 后):**

```python
sub_map: dict[str, MaterialSubSummary] = {}    # material_code -> summary
if material_codes:
    sub_result = await db.execute(
        select(SubcontractOrderDetail, SubcontractOrder)
        .join(
            SubcontractOrder,
            SubcontractOrder.erp_order_id == SubcontractOrderDetail.erp_order_id,
        )
        .where(
            SubcontractOrderDetail.sale_order_no == order_no,
            SubcontractOrderDetail.material_id.isnot(None),
            SubcontractOrder.voided_flag != 1,
        )
    )
    # 把行按 material_code 聚合后调 _summarize_subs
    ...
```

实际 join 走 `material_id → Material.erp_material_id → Material.material_code`。简化:`material_id` 与 `erp_material_id` 在 SQL 上直接相等匹配,所以一次 join:

```python
join(Material, Material.erp_material_id == SubcontractOrderDetail.material_id)
.where(Material.material_code.in_(material_codes))
```

**Step B(循环内,line 475 附近):**

对 `bill_type == 11012` 的行:
```python
if bill_type == 11012:
    sub_summary = sub_map.get(plan.material_code)
    pos = []
    po_summary = None
    status = _status_for_plan(bill_type, po_summary=None, sub_summary=sub_summary)
    received_qty = sub_summary.received_qty if sub_summary else None
    po_qty = sub_summary.po_qty if sub_summary else None
    po_count = sub_summary.po_count if sub_summary else 0
    # supplier / ETA / inspection 字段也按 sub_summary 填
else:
    # 既有路径完全不变
    pos = po_map.get(plan.material_code, [])
    po_summary = _summarize_pos(pos)
    status = _status_for_plan(bill_type, po_summary)
    received_qty = po_summary.received_qty if po_summary else None
    po_qty = po_summary.po_qty if po_summary else None
    po_count = po_summary.po_count if po_summary else 0
```

**Step C(库存满足段,line 493-510):**
现有逻辑对所有 plan 统一基于 `available_stock_map` 检查库存是否覆盖净需求。
净需求 `base_qty - received_qty` 在 bill_type=11012 时仍以 `received_qty = sub_summary.received_qty` 代入,无需改。

### 3.4 影响传播
- `_get_plan_order_material_items` 是 `get_order_materials` 的核心
- `get_order_materials` 既被 `/materials/kit-analysis`(订单级)也被 `/materials/kit-analysis/{order_no}/product-breakdown`(产品 BOM 树,via `mat_by_code`)调用
- 修复后:
  - **订单级列表**(主表 齐套率/已到齐/部分到/未到 列)同步修正 ✓
  - **产品 BOM 树的物料 KitAnalysisMaterialItem**(`bom_trees[*]`)同步修正 ✓
  - **新 `/product-bom-flat` 端点** 的物料状态同步修正 ✓

所有已有调用点透明受益,零迁移成本。

## 4. 数据流总览

```
订单页面打开
  → 后端 get_order_product_breakdown(order_no)
    → get_order_materials(order_no)
      → _get_plan_order_material_items(order_no)         # ★ 本次改造点
        → select MrpPlanOrder where sale_order_no = X
        → select PurchaseOrder (既有 PO 聚合)
        → select SubcontractOrderDetail join … where sale_order_no = X  # ★ 新增
        → 组装 sub_map[material_code] = MaterialSubSummary
        → 循环每行 plan:
            if bill_type == 11012:
                读 sub_map 算 status / received / po_qty
            else:
                读 po_summary 算 status / received / po_qty  (既有)
      → KitAnalysisItem 汇总 → OrderProductKitBreakdownOut
  → 前端 BomMaterialTable 渲染:委外行 status 显示 "已到齐 / 部分到 / 待到料 / 未下单"
```

## 5. 验证步骤

1. **后端导入烟测**:
   ```
   cd backend && python -c "from app.services.order.order_materials_service import _summarize_subs, _subcontract_status, MaterialSubSummary; from app.services.material.kit_analysis_service import _get_plan_order_material_items, _status_for_plan; print('ok')"
   ```
   退出码 0。

2. **单元级正确性(合成数据,无需 DB)**:
   ```
   python -c "
   from app.services.order.order_materials_service import _subcontract_status, MaterialSubSummary
   from decimal import Decimal
   print(_subcontract_status(None))                                  # not_ordered
   print(_subcontract_status(MaterialSubSummary(po_no='SC1', po_qty=Decimal('10'), received_qty=Decimal('0'), po_count=1)))  # pending
   print(_subcontract_status(MaterialSubSummary(po_no='SC1', po_qty=Decimal('10'), received_qty=Decimal('5'), po_count=1)))  # partial_received
   print(_subcontract_status(MaterialSubSummary(po_no='SC1', po_qty=Decimal('10'), received_qty=Decimal('10'), po_count=1))) # fully_received
   "
   ```
   期望 4 个输出:`not_ordered` / `pending` / `partial_received` / `fully_received`,退出码 0。

3. **后端 typecheck**: `python -c "from app.main import app"` 通过(无回归)。

4. **前端 typecheck**: `cd frontend && npm run build` 退出码 0(无前端改动)。

5. **端到端(浏览器手动测试,由用户执行)**:
   - 找一个既有委外 BOM 子项又有 PO/SubcontractOrder 数据的订单(可向 DBA 询问样例 HJ 编号)
   - 浏览器「齐套分析」→「展开」→「选中产品」
   - BOM 表中 bill_type=11012 行的:
     - 「状态」应为 `已到齐 / 部分到 / 待到料 / 未下单` 中之一,与 `SubcontractOrderDetail.received_qty` 一致
     - 「下单量」≈ SubcontractOrderDetail.qty(可能有少量 sql sum 浮点)
     - 「已收」≈ SubcontractOrderDetail.received_qty
     - 「短缺」应基于上述替换后的下单/已收计算
   - 订单级表的「齐套率」「已到齐 / 部分到 / 未到」应同步变化(向上取整)

## 6. 风险与回滚

- **风险 A: 库存满足段逻辑没特殊处理 bill_type=11012**: 净需求用 `base_qty - sub_received_qty` 代入即可;`_status_for_plan` 已经替代。已验证:净值口径与 PO 路径一致。
- **风险 B: 委外订单 voided/closed 仍被纳入统计**: SQL 已加 `voided_flag != 1` 过滤;`closed_flag = 1` 保留(已关闭但仍反映出过货的订单,无需排除);`mrp_closed_flag = 1` 也保留(同口径)。
- **风险 C: 订单级齐套率意外上跳**: 这是预期行为(原本就是 bug),但如担心误导,在前端 Tooltip 加一行说明非本次范围,留后续 issue。
- **回滚**: revert 涉及的 2 个 commit 即可,既有 PO 路径完全不变,无副作用。

## 7. 与既有计划的关系

本次改动与刚合并的「BOM 物料齐套表列排序与筛选」(commit 6a8fbd5..e0b618d)互补:
- 上次改的是「如何展示」(扁平表 + 13 列排序/筛选)
- 本次改的是「如何计算」(status 字段的来源逻辑)

两条改动互不冲突,可以独立合并。