# Design: 滚动态基准库存 (Rolling Available Stock)

**Date:** 2026-07-14
**Status:** Approved, pending implementation
**Scope:** 扩展物料盘点 (`scm_inventory_check`) — 新增 `available_qty` 列实现"推叠"链式累计:完成一张盘点单后,该物料的"可用库存"被推入链,下一张盘点单的 `system_qty` 来自该链上最新值,缺时回退到 `scm_inventory.qty_on_hand`。

---

## 1. Background

### 老板的需求
- 公式: **盘点数 - 应盘数 = 可用库存数**
- 应用: 下一个订单盘点该物料时,`system_qty` = 该物料上一个完成单产生的 `available_qty`
- 失败场景: 多个订单用同一物料,各自看 raw `qty_on_hand` → 多个订单都按 1000 算"够",实际总共只有 1000

### 既有实现
- `scm_inventory_check_item.system_qty` = 创建盘点单时一次性快照自 `scm_inventory.qty_on_hand`,之后永不变
- 每次盘点独立,前一张盘点不影响下一张的 `system_qty`

---

## 2. 新模型 (老板字面公式,Latest Wins)

### 2.1 公式

```
盘后可用 = actual_qty - req_qty   (本单盈亏,与 system_qty 无关)
后端 available_qty = actual_qty - req_qty   (完结时写入,作为下一单 system_qty 来源)
下一单 system_qty = 上一张完成单的 available_qty (latest wins,不累加)
```

每张完成单贡献自己的 `actual - req` 给链,**不累加**;下一单只看 latest。

### 2.2 行为示例

```
qty_on_hand(M1) = 1000

订单 A 创建盘点 (无前驱):
  system_qty = 1000 (来自 qty_on_hand)
  user 录 actual=950, req=500
  diff = 950 - 1000 = -50
  预览 "盘后可用" = 950 - 500 = 450    ← 老板字面公式
完成 A:
  available_qty = 450   入链

订单 B 创建盘点 (前驱是 A):
  system_qty = 450   ← 来自 A 的 available_qty
  user 录 actual=440, req=200
  diff = 440 - 450 = -10
  预览 "盘后可用" = 440 - 200 = 240   ← 不累加
完成 B:
  available_qty = 240   入链(替换 A 的位置)

订单 C 创建盘点:
  system_qty = 240   ← 来自 B 的 available_qty
  ...
```

**关键不变量**: 预览 "盘后可用" 和后端 `available_qty` 使用**完全相同**的公式 `actual - req`。UI 看到的就是后端存的,没有第二个语义。

---

## 3. 数据模型变更

### `scm_inventory_check_item` 新增 1 列

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `available_qty` | Numeric(18,4) | nullable | 完结时计算 = system_qty - req_qty + actual_qty |

- 完结前为 NULL
- 完结后写入,作为下一张单 system_qty 的"前驱"
- 历史数据全部为 NULL,不入链
- 取消的盘点单:该列保持 NULL(或忽略),不入链

**零迁移风险**:仅加一列,nullable,默认值 NULL,不影响既有数据。

---

## 4. 计算逻辑

### 4.1 完成时 (`complete_stock_check`)

```python
for item in check.items:
    if item.actual_qty is None:
        raise ValueError(f"物料 {item.material_code} 还未录入实盘数")
    if item.req_qty is not None:
        item.available_qty = (
            Decimal(str(item.actual_qty))
            - Decimal(str(item.req_qty))
        )
```

**前置校验**:所有 `actual_qty` 必须非 null(允许 0)。

**公式含义**:`available_qty` 记录本单的"盈亏"(实盘比需求多多少或少多少),不包含 system_qty。这是老板原话"`盘 - 应 = 可用`"的字面实现。

### 4.2 创建时 (`create_stock_check_from_order`)

```sql
SELECT DISTINCT ON (sci.material_id)
       sci.material_id, sci.available_qty
FROM scm_inventory_check_item sci
JOIN scm_inventory_check sc ON sc.id = sci.check_id
WHERE sci.material_id = ANY(:material_ids)
  AND sc.status = 'completed'
  AND sci.available_qty IS NOT NULL
ORDER BY sci.material_id, sc.completed_at DESC;
```

返回 dict: `{material_id: available_qty}`。未命中的 material_id,创建时 fallback 到 `scm_inventory.qty_on_hand`。

**Latest wins 语义**:同一物料的多张完成单,以 `completed_at DESC` 取最新一张的 `available_qty`,不累加,不汇总。

---

## 5. API 变更

### `StockCheckItemOut` (Pydantic)

新增字段:
```python
available_qty: Optional[Decimal] = None  # 完结时计算,未完结为 None
```

### 端点

**`POST /materials/stock-check/from-order/{order_no}`**:
- 行为变化:对每个物料,先查 available,命中用之,未命中用 qty_on_hand
- 响应:items 中 `system_qty` 现在是"可用库存",`available_qty` 为 null(未完结)

**`POST /materials/stock-check/{check_id}/complete`**:
- 行为变化:
  1. 校验所有 items 的 `actual_qty` 非 null,否则 400
  2. 完结时计算每个 item 的 `available_qty`,写入库
  3. status='completed',已盘数、总差异等头部汇总刷新(原有)
- 响应:items 中 `available_qty` 已有值

**其他端点**:无变化。

---

## 6. 前端变更

### 6.1 物料表列

| 列 | 标题 | 数据来源 | 备注 |
|---|---|---|---|
| 物料编码 / 名称 / 规格 / 单位 | (不变) | item.material_* | |
| 应盘数 | (不变) | item.req_qty | |
| **可用库存** (原"库存数") | "可用库存" | item.system_qty | 改语义,可能来自上一张单 |
| 盘点数 | (不变) | item.actual_qty | 用户录入 |
| 差异 | (不变) | item.diff_qty | 实际-可用 |
| **盘后可用** (新增) | "盘后可用" | 实时计算 `system_qty - req_qty + actual_qty` | 完结后此值会入链 |
| 已盘 / 标记时间 / 标记人 / 备注 / 操作 | (不变) | | |

### 6.2 完结前预检

```ts
const incomplete = items.filter(it => it.actual_qty == null)
if (incomplete.length > 0) {
  message.error(`还有 ${incomplete.length} 行未录入实盘数,请先填写后再标记完成`)
  return
}
```

### 6.3 is_checked 与 actual_qty 联动

`actual_qty` 为 null 时,`is_checked` 复选框禁用,防止漏填。

---

## 7. 边界场景

| 场景 | 行为 |
|---|---|
| 物料首次被盘 | 无前驱 → `system_qty` = `qty_on_hand` |
| 上张单 cancelled | status≠completed → 不在链 → fallback qty_on_hand |
| 上张单 in_progress / open | 同上 |
| 同订单被重盘(新 check) | 旧 check 若已 completed 仍在链,新 check 拿其 available(以 completed_at 排序,最新者生效) |
| 完成时 actual_qty null | 拒绝(400 + UI 预检) |
| 物料从未入库(`qty_on_hand`=0) | 第一张单的 system_qty=0,正常处理 |
| 同一物料跨多产品行的订单 | 当前实现已按 material_id 聚合,新逻辑兼容 |

---

## 8. 文件清单 (4 后端 + 1 前端)

| 操作 | 文件 |
|---|---|
| 修改 | `backend/app/models/material/inventory_check.py` (+ available_qty 字段) |
| 修改 | `backend/init_database.py` (migrate_columns 加 `scm_inventory_check_item.available_qty`) |
| 修改 | `backend/app/schemas/material/stock_check.py` (StockCheckItemOut 加 available_qty) |
| 修改 | `backend/app/services/material/stock_check_service.py` (+ _get_available_by_material_id;改 create;改 complete) |
| 修改 | `frontend/src/pages/OrderDelivery/StockCheck/index.tsx` (列名+预览列+校验) |

---

## 9. 验证清单

1. `python init_database.py` 跑通,新列被加
2. `npm run build` 通过
3. Smoke test 完整链路:
   - 订单 A 创建 → system_qty = qty_on_hand(假设 1000)
   - 录入 actual=950, req=500, 完成 → available_qty = 1450 入库
   - 订单 B 创建 → system_qty = 1450(来自 A)
   - 录入 actual=440, req=200, 完成 → available_qty = 1690 入库
   - 订单 C 创建 → system_qty = 1690
4. 取消的盘点单:不入链
5. 同一物料 in_progress 的盘点单:不入链
6. 完结时 actual_qty 空:400 错误 + UI 拒绝
7. 预览"盘后可用"实时随 actual 变化
8. 历史数据:旧盘点单 available_qty=null,新盘点单按新规则

---

## 10. 风险 / 范围外

- **不写 scm_inventory.qty_on_hand**:available 是 derived 概念,避免反同步问题
- **不调账**:同现有"不调账"设计
- **不递归跨订单回溯**:链只看 latest by completed_at,不累加所有历史单的 available
- **不支持手动改 available_qty**:只能通过 complete 触发计算
- **不做数据回填/重算脚本**:历史单默认 available_qty=null,从今天开始入链
