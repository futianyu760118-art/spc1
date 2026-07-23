# 委外 BOM 子项齐套状态修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 对 `MrpPlanOrder.bill_type = 11012` 的 BOM 子项,改用 `SubcontractOrderDetail` 的 `received_qty` / `qty` 推导齐套状态(替换当前走 PO 路径导致永久 `not_ordered` 的 bug),并把「下单量」「已收」列也替换为委外口径。

**Architecture:** 在 `order_materials_service.py` 新增 `MaterialSubSummary` dataclass、`_summarize_subs`、`_subcontract_status`(对齐既有 `_summarize_pos` / `_status` 形态);在 `kit_analysis_service.py` 修改 `_status_for_plan` 接受 `sub_summary`;在 `_get_plan_order_material_items` 增加一次 `SubcontractOrderDetail join Material` 查询,并对 `bill_type == 11012` 的 plan 行走委外分支。

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy + asyncpg, dataclasses, decimal.

**Spec:** `docs/superpowers/specs/2026-07-22-subcontract-bom-kit-status-design.md`

---

## Global Constraints

- 不改 schema / 不改 `init_database.py`
- 不改前端(13 列 BOM 表沿用现有渲染)
- 不引入新依赖
- 既有 PO 路径(11010 / 11011 / 缺 bill_type)零改动
- 路由、菜单、权限不变
- conda python 路径: `D:\software\miniconda3\python.exe`
- 子代理提交消息前缀统一: `fix(kit-analysis): ...` 或 `feat(kit-analysis): ...`

---

## Task 1: 新增 MaterialSubSummary dataclass + _summarize_subs + _subcontract_status

**Files:**
- Edit: `backend/app/services/order/order_materials_service.py`

**Step 1.1:** 在第 86 行(已有 `MaterialPoSummary` dataclass 定义附近,dataclass 同区块)查清现有 `@dataclass` 块的位置。

若 `MaterialPoSummary` 已在文件中,直接在其下方插入:

```python
@dataclass
class MaterialSubSummary:
    """按 (sale_order_no, material_code) 聚合的委外订单汇总。平行于 MaterialPoSummary。"""
    po_no: Optional[str] = None                       # 委外订单 bill_no(多张以 ", " 拼接)
    supplier_name: Optional[str] = None
    po_qty: Optional[Decimal] = None                  # 委外订单数量(等同总量)
    received_qty: Optional[Decimal] = None            # 已收数量(完工入库)
    first_eta: Optional[date] = None
    latest_eta: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    inspection_date: Optional[date] = None
    po_count: int = 0
    is_closed: int = 0
```

**Step 1.2:** 在 `_summarize_pos` 函数(line 114-134)正下方插入 `_summarize_subs`:

```python
def _summarize_subs(subs: list) -> Optional[MaterialSubSummary]:
    """聚合多条 SubcontractOrderDetail 行。同 (material_code) 已在外层做好分组,这里只是聚合。

    subs 每条形如 SimpleNamespace(qty, received_qty, bill_no, supplier_name, eta, audit_date, ...)
    """
    if not subs:
        return None
    return MaterialSubSummary(
        po_no=", ".join(dict.fromkeys([s.bill_no for s in subs if getattr(s, "bill_no", None)])) or None,
        supplier_name=_pick_first([getattr(s, "supplier_name", None) for s in subs]),
        po_qty=_sum_qty([getattr(s, "qty", None) for s in subs]),
        received_qty=_sum_qty([getattr(s, "received_qty", None) for s in subs]),
        first_eta=min([s.eta for s in subs if getattr(s, "eta", None)], default=None) if subs else None,
        latest_eta=max([s.eta for s in subs if getattr(s, "eta", None)], default=None) if subs else None,
        actual_arrival_date=max([s.actual_arrival_date for s in subs if getattr(s, "actual_arrival_date", None)], default=None) if subs else None,
        inspection_date=max([s.inspection_date for s in subs if getattr(s, "inspection_date", None)], default=None) if subs else None,
        po_count=len(subs),
        is_closed=1 if any(getattr(s, "closed_flag", 0) for s in subs) else 0,
    )


def _subcontract_status(sub_summary: Optional[MaterialSubSummary]) -> str:
    """委外物料齐套状态。4 出口,与 _status 对齐:已到齐/部分到/待到料/未下单。"""
    if not sub_summary or sub_summary.po_count == 0:
        return "not_ordered"
    received = sub_summary.received_qty
    qty = sub_summary.po_qty
    if received is not None and received > 0:
        if qty is not None and received >= qty:
            return "fully_received"
        return "partial_received"
    return "pending"
```

**Step 1.3:** Verify with:

```
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "
from app.services.order.order_materials_service import _summarize_subs, _subcontract_status, MaterialSubSummary
from decimal import Decimal
print(_subcontract_status(None))
print(_subcontract_status(MaterialSubSummary(po_no='SC1', po_qty=Decimal('10'), received_qty=Decimal('0'), po_count=1)))
print(_subcontract_status(MaterialSubSummary(po_no='SC1', po_qty=Decimal('10'), received_qty=Decimal('5'), po_count=1)))
print(_subcontract_status(MaterialSubSummary(po_no='SC1', po_qty=Decimal('10'), received_qty=Decimal('10'), po_count=1)))
"
```

Expected output:
```
not_ordered
pending
partial_received
fully_received
```

Exit code 0.

**Step 1.4:** Commit: `feat(kit-analysis): add MaterialSubSummary + subcontract status helper`

---

## Task 2: 修改 _status_for_plan 接受 sub_summary

**Files:**
- Edit: `backend/app/services/material/kit_analysis_service.py`

**Step 2.1:** 在 import 块补两行:

```python
from app.models.material.purchase_order import PurchaseOrder
from app.models.material.subcontract_order import SubcontractOrder
from app.models.material.subcontract_order_detail import SubcontractOrderDetail
```

(保证三个 import 按字母序排列,`subcontract_order` 排在 `subcontract_order_detail` 前)

**Step 2.2:** 把 import from order_materials_service 块(line 31-39)扩展为:

```python
from app.services.order.order_materials_service import (
    STATUS_LABELS,
    _kit_met,
    _material_property_label,
    _status,
    _subcontract_status,
    _summarize_pos,
    _summarize_subs,
    _to_float,
    _expand_bom_tree,
)
```

(按字母序加入 `_subcontract_status`、`_summarize_subs`)

**Step 2.3:** 修改 `_status_for_plan` 函数(line 100-107),把签名加一个可选参数并加 bill_type=11012 分支:

```python
def _status_for_plan(
    bill_type: Optional[int],
    po_summary,
    sub_summary=None,
) -> str:
    """根据计划订单单据类型推导物料状态。

    11012(委外):不走 PO 路径,改用委外订单 received/qty。
    11010(采购):走 PO 路径。
    11011(自制):走 PO 路径,无 PO 视为自制未排产/未关联。
    """
    if bill_type == 11012:
        return _subcontract_status(sub_summary)
    material_property = BILL_TYPE_TO_MATERIAL_PROPERTY.get(bill_type, 1)
    return _status(material_property, po_summary)
```

**Step 2.4:** Verify:

```
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "
from app.services.material.kit_analysis_service import _status_for_plan
from app.services.order.order_materials_service import MaterialSubSummary
from decimal import Decimal
# bill_type=11012 + 无 sub → not_ordered
print(_status_for_plan(11012, None, None))
# bill_type=11012 + 部分到
print(_status_for_plan(11012, None, MaterialSubSummary(po_count=1, po_qty=Decimal('10'), received_qty=Decimal('5'))))
# bill_type=11010 走 PO 路径不受影响
print(_status_for_plan(11010, None, None))
"
```

Expected:
```
not_ordered
partial_received
not_ordered
```

**Step 2.5:** Commit: `feat(kit-analysis): _status_for_plan accepts sub_summary for bill_type=11012`

---

## Task 3: _get_plan_order_material_items 加入委外查询与分支

**Files:**
- Edit: `backend/app/services/material/kit_analysis_service.py`

**Step 3.1:** 在 `_get_plan_order_material_items` 中(line 448 附近,`po_map` 块之后,line 462 `available_stock_map` 之前),追加一段 sub 查询与聚合:

在 `po_map: dict[str, list[PurchaseOrder]] = {}` 块之后(找到该段并在其后紧跟插入):

```python
    # 委外订单明细(用于 bill_type=11012 物料的齐套状态推导)
    sub_map: dict[str, MaterialSubSummary] = {}
    if material_codes:
        sub_result = await db.execute(
            select(
                SubcontractOrderDetail.qty,
                SubcontractOrderDetail.received_qty,
                SubcontractOrder.bill_no,
                SubcontractOrderDetail.sale_order_no,
                Material.material_code.label("material_code"),
                SubcontractOrder.closed_flag,
            )
            .join(
                Material,
                Material.erp_material_id == SubcontractOrderDetail.material_id,
            )
            .join(
                SubcontractOrder,
                SubcontractOrder.erp_order_id == SubcontractOrderDetail.erp_order_id,
            )
            .where(
                SubcontractOrderDetail.sale_order_no == order_no,
                Material.material_code.in_(material_codes),
                SubcontractOrder.voided_flag != 1,
            )
        )
        # 按 material_code 分桶
        grouped: dict[str, list] = {}
        for row in sub_result.all():
            mc = row.material_code
            grouped.setdefault(mc, []).append(row)
        for mc, rows in grouped.items():
            sub_map[mc] = _summarize_subs([
                SimpleNamespace(
                    qty=row.qty,
                    received_qty=row.received_qty,
                    bill_no=row.bill_no,
                    closed_flag=row.closed_flag,
                )
                for row in rows
            ])
```

(注意 `SimpleNamespace` 已在 line 4 import,如缺请在第 4 行确认 `from types import SimpleNamespace`.)

**Step 3.2:** 在循环(line 467-562)中,替换 `pos = po_map.get(plan.material_code, [])` 周围的逻辑:

找到这段:
```python
        pos = po_map.get(plan.material_code, [])
        po_summary = _summarize_pos(pos)
        bill_type = plan.bill_type
        master = master_map.get(plan.material_code)
        # 物料属性优先取计划订单自身的字段（来源 K3 FErpClsID），缺失时回退推导
        material_property = plan.material_property
        if material_property is None:
            material_property = _resolve_material_property(bill_type, po_summary, master)
        status = _status_for_plan(bill_type, po_summary)

        received_qty = po_summary.received_qty if po_summary else None
        po_qty = po_summary.po_qty if po_summary else None
        ...
```

替换为:

```python
        bill_type = plan.bill_type
        master = master_map.get(plan.material_code)
        if bill_type == 11012:
            # 委外:不看 PO,从委外汇总读
            sub_summary = sub_map.get(plan.material_code)
            po_summary = None
            pos = []
            po_count = sub_summary.po_count if sub_summary else 0
            status = _status_for_plan(bill_type, po_summary=None, sub_summary=sub_summary)
            received_qty = sub_summary.received_qty if sub_summary else None
            po_qty = sub_summary.po_qty if sub_summary else None
            latest_eta = sub_summary.latest_eta if sub_summary else None
            first_eta = sub_summary.first_eta if sub_summary else None
            actual_arrival_date = sub_summary.actual_arrival_date if sub_summary else None
            inspection_date = sub_summary.inspection_date if sub_summary else None
            po_no = sub_summary.po_no if sub_summary else None
            supplier_name = sub_summary.supplier_name if sub_summary else None
            material_property = plan.material_property if plan.material_property is not None else 3  # 委外
        else:
            pos = po_map.get(plan.material_code, [])
            po_summary = _summarize_pos(pos)
            po_count = po_summary.po_count if po_summary else 0
            material_property = plan.material_property
            if material_property is None:
                material_property = _resolve_material_property(bill_type, po_summary, master)
            status = _status_for_plan(bill_type, po_summary)
            received_qty = po_summary.received_qty if po_summary else None
            po_qty = po_summary.po_qty if po_summary else None
            latest_eta = po_summary.latest_eta if po_summary else None
            first_eta = po_summary.first_eta if po_summary else None
            actual_arrival_date = po_summary.actual_arrival_date if po_summary else None
            inspection_date = po_summary.inspection_date if po_summary else None
            po_no = po_summary.po_no if po_summary else None
            supplier_name = po_summary.supplier_name if po_summary else None
```

**Step 3.3:** 找到紧随其后的 `_status_for_plan` 行(原 line 483)与该行的后续 field 取值代码(line 485-491 现可能已被替换),检查 `po_count` 字段下游是否还有使用。若有保留赋值;否则在 KitAnalysisMaterialItem 构造时确保传入新值。

实际:查看 KitAnalysisMaterialItem schema(line 244 附近)的字段,可能 `po_count` 也需要从 `po_summary.po_count` 或 `sub_summary.po_count` 取。**如果下游用 `po_count` 字段,从 `po_count` 变量取值**(Task 3.2 已抽出该变量)。

**Step 3.4:** Verify: 整体函数仍能 import 通过。

```
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.services.material.kit_analysis_service import _get_plan_order_material_items, _status_for_plan; print('ok')"
```

Exit 0.

**Step 3.5:** Commit: `feat(kit-analysis): route bill_type=11012 through SubcontractOrderDetail in kit status pipeline`

---

## Task 4: 完整 typecheck + 后端 API 烟测

**Step 4.1:** App import 全链路:

```
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -c "from app.main import app; print('routes=', len(app.routes))"
```

Expected: prints `routes=` with a positive integer (count should be 1 more than before, since `/materials/kit-analysis/{order_no}/product-bom-flat` was added in prior session), exit 0.

**Step 4.2:** 前端 build (no frontend changes, but must remain unchanged):

```
cd D:\wanghuazheng\project\SPC-v2\frontend
npm run build
```

Expected: exit 0, no new errors.

**Step 4.3:** 端到端浏览器测试(由用户执行,见 §Manual Test Below):

启动后端 + 前端,登录 admin → 齐套分析 → 展开一个有委外 BOM 子项的订单(可向 DBA 询问样例订单号)→ 选中产品 → 验证 bill_type=11012 行的「状态」「下单量」「已收」「短缺」反映委外收料进度。

---

## Manual Test (Optional)

After deploying changes:

1. Start backend:
```
cd D:\wanghuazheng\project\SPC-v2\backend
& "D:\software\miniconda3\python.exe" -m uvicorn app.main:app --reload --port 8000
```

2. Login + smoke test endpoint:
```
TOK=$(curl -s -X POST http://localhost:8000/api/v1/basicdata/auth/login -d 'login_type=employee&username=admin&password=admin123' | jq -r '.data.access_token')
curl -H "Authorization: Bearer $TOK" 'http://localhost:8000/api/v1/materials/kit-analysis/HJ-xxx/materials?material_code=委外物料编码' | jq '.data[0] | {status, po_qty, received_qty, material_property}'
```

Expected: `status` is one of `not_ordered / pending / partial_received / fully_received`, `material_property: 3`, `po_qty ≈ SubcontractOrderDetail.qty.sum()`, `received_qty ≈ SubcontractOrderDetail.received_qty.sum()`.

## Rollback

Revert commits 1, 2, 3 to roll back. All three are surgical and isolated to the kit-status pipeline. No schema or interface changes, so no follow-up migrations required.