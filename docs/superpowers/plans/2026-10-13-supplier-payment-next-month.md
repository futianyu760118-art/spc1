# 供应商付款排程 — 下月应付金额 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 供应商付款排程列表新增「下月应付金额」列：按供应商各自最晚付款申请月份为基准，取其后第一个有有效应付的排款月合计（下月没有就下下月，依此类推），列表 + 导出展示。

**Architecture:** purchase_invoice 新增 `payment_apply_date` 列（同步 SQL 加选付款申请主表 `aa.FDate`），服务层纯函数 `_compute_next_month_due` 按供应商发票聚合计算，列表/导出接口内嵌返回，前端直接渲染。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy(asyncpg) + Pydantic v2；React + Ant Design 5；pytest。

## Global Constraints

- 后端响应必须 `{ code, message, data }`（`ResponseModel`）。
- 新列必须同时加 SQLAlchemy model 与 `init_database.py` `migrate_columns`（Alembic 只是旁路，容器重启真相源是 init_database.py）。
- 计算必须遵守 `_not_paid_clause()` / sync_filters 与 `_effective_payable` 口径；不改 ERP 同步代码逻辑，只改 SQL 配置文本。
- 前端唯一校验命令 `npm run build`；仓库无 lint。
- 后端测试命令 `cd backend && python -m pytest`。
- 禁止 console.log / print 调试残留；不留注释掉的旧代码。

---

## Task 1: 模型加列 + 迁移登记

**文件 1**: `backend/app/models/material/purchase_invoice.py`

在 `payment_order_id` 列后新增：

```python
    payment_apply_date = Column(Date, nullable=True, comment="付款申请日期")
```

**文件 2**: `backend/init_database.py` — `migrate_columns` dict 增加新表项（在 `"purchase_invoice"` 不存在的情况下新增条目；搜索确认现无该 key，则插入）：

```python
            "purchase_invoice": {
                "payment_apply_date": "DATE",
            },
```

**文件 3**: `backend/alembic/versions/0119_purchase_invoice_payment_apply_date.py`（新文件，down_revision="0118"）：

```python
"""add payment_apply_date to purchase_invoice

Revision ID: 0119
Revises: 0118
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0119'
down_revision: Union[str, Sequence[str], None] = '0118'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_invoice', sa.Column('payment_apply_date', sa.Date(), nullable=True, comment='付款申请日期'))


def downgrade() -> None:
    op.drop_column('purchase_invoice', 'payment_apply_date')
```

**验证**：`docker exec -w /app spc-v2-backend-1 python init_database.py` 输出 `purchase_invoice: ADD COLUMN payment_apply_date` 类日志且无报错；`python -m pytest tests/unit -q` 通过。

---

## Task 2: 同步 SQL 配置更新（种子 + 现有库一次性脚本）

**文件 1**: `backend/init_database.py` seed `purchase_invoices` 模板（约 2222 行）：TODO 占位 SQL 的返回字段注释补 `payment_apply_date`，并给该模板 `field_mapping_json` 保持 None 不变（模板未启用，只补注释）。

**文件 2**: `backend/scripts/oneoff/update_purchase_invoice_sync_payment_apply_date.py`（新文件，用后删）：

```python
"""一次性：purchase_invoices 同步 SQL 加选付款申请日期并写字段映射。最后验证: 2026-10-13"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio
import json

from sqlalchemy import text

from app.core.database import engine


NEW_COL = "aa.FDate AS 付款申请日期"
NEW_MAP_ENTRY = {"target": "payment_apply_date", "remark": "付款申请主表的单据日期字段"}
ANCHOR = "aa.FPayBillID_CN AS 付款单Id,"


async def main():
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT sql_text, field_mapping_json FROM sync_sql_config WHERE sync_type='purchase_invoices'")
        )).mappings().first()
        if row is None:
            print("purchase_invoices config not found, skip")
            return
        sql_text = row["sql_text"] or ""
        if "付款申请日期" in sql_text:
            print("SQL already contains 付款申请日期, skip sql update")
        elif ANCHOR in sql_text:
            new_sql = sql_text.replace(ANCHOR, ANCHOR + "\n  " + NEW_COL + ",", 1)
            await conn.execute(text(
                "UPDATE sync_sql_config SET sql_text=:s, updated_at=NOW() WHERE sync_type='purchase_invoices'"
            ), {"s": new_sql})
            print("SQL updated: added 付款申请日期")
        else:
            print("ANCHOR not found, skip sql update (manual needed)")
        mapping = json.loads(row["field_mapping_json"] or "{}")
        if "付款申请日期" not in mapping:
            mapping["付款申请日期"] = NEW_MAP_ENTRY
            await conn.execute(text(
                "UPDATE sync_sql_config SET field_mapping_json=:m, updated_at=NOW() WHERE sync_type='purchase_invoices'"
            ), {"m": json.dumps(mapping, ensure_ascii=False)})
            print("mapping updated")
        else:
            print("mapping already has 付款申请日期, skip")
        await conn.commit()


if __name__ == "__main__":
    asyncio.run(main())
```

**验证**：`docker cp` 该脚本进容器并执行，输出 updated；再查 `sync_sql_config` 确认 SELECT 含 `付款申请日期` 且 mapping 含 target `payment_apply_date`。执行后删除该脚本文件。

---

## Task 3: 服务层计算函数 + 数据查询加列

**文件**: `backend/app/services/material/supplier_payment_service.py`

1. `_get_supplier_all_invoices` 的 select 列表在 `payment_order_id` 后加 `PurchaseInvoice.payment_apply_date,`；构建 `invoice_map` 的 dict 中加：

```python
            'payment_apply_date': r['payment_apply_date'],
```

2. 在 `_compute_overdue_by_month` 之后新增纯函数：

```python
def _compute_next_month_due(invoices: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[Decimal]]:
    """计算下月应付金额与所属月份。

    付款进度月 = 最晚付款申请日期所在月；
    下月应付 = 进度月之后第一个有效应付>0的排款月合计；
    无付款申请记录时取最早应付月；找不到返回 (None, None)。
    """
    month_map: Dict[str, Decimal] = {}
    progress_month: Optional[str] = None
    for inv in invoices:
        inv_date = inv.get('invoice_date')
        if not inv_date:
            continue
        pm = _compute_payment_month(inv_date, inv.get('payment_term'))
        if not pm:
            continue
        remain = _effective_payable(inv)
        if remain > 0:
            month_map[pm] = month_map.get(pm, Decimal('0')) + remain
        apply_date = inv.get('payment_apply_date')
        if apply_date:
            if isinstance(apply_date, str):
                try:
                    apply_date = datetime.strptime(apply_date, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    apply_date = None
            if apply_date:
                am = apply_date.strftime('%Y-%m')
                if progress_month is None or am > progress_month:
                    progress_month = am
    if not month_map:
        return None, None
    months = sorted(month_map)
    if progress_month:
        for m in months:
            if m > progress_month:
                return m, month_map[m]
        return None, None
    return months[0], month_map[months[0]]
```

3. 新增附着函数（与 `_attach_overdue` 并列）：

```python
def _attach_next_month_due(
    items: List[Dict[str, Any]],
    all_invoices_map: Dict[str, List[Dict[str, Any]]],
) -> None:
    """为每个聚合行附上 next_month 与 next_month_due。"""
    for it in items:
        next_month, next_due = _compute_next_month_due(all_invoices_map.get(it['supplier_code'], []))
        it['next_month'] = next_month
        it['next_month_due'] = next_due
```

4. `get_supplier_payment_list`：在 `_attach_overdue(items, all_invoices_map)` 后加 `_attach_next_month_due(items, all_invoices_map)`。

5. `get_supplier_payment_export`：同样在 `_attach_overdue` 后加 `_attach_next_month_due(items, all_invoices_map)`。

6. `SORT_LABELS` 集合加 `'next_month_due', 'next_month'`。

7. `_format_item` 返回 dict 中加：

```python
        'next_month': item.get('next_month'),
        'next_month_due': float(item['next_month_due'].quantize(Decimal('0.01'))) if item.get('next_month_due') is not None else None,
```

8. `EXPORT_COLUMNS` 在 `overdue_total` 后加：

```python
    ExportColumn('next_month', '下月应付月份', 12),
    ExportColumn('next_month_due', '下月应付金额', 14),
```

9. export_rows 循环内加：

```python
            'next_month': it.get('next_month') or '',
            'next_month_due': it.get('next_month_due', 0),
```

**验证**：`python -m pytest tests/unit -q`；有 DB 时用容器跑列表接口抽查（见 Task 6）。

---

## Task 4: Schema 增加字段

**文件**: `backend/app/schemas/material/schemas.py` — `SupplierPaymentOut` 在 `overdue_by_month` 后加：

```python
    next_month: Optional[str] = None
    next_month_due: Optional[float] = None
```

**验证**：`python -m pytest tests/unit -q` 不因 schema 报错。

---

## Task 5: 前端新列

**文件**: `frontend/src/pages/MaterialCenter/SupplierPayment/index.tsx`

1. `SupplierPaymentRow` 接口加：

```typescript
  next_month: string | null
  next_month_due: number | null
```

2. 在「实际到期未付」列之后新增列：

```tsx
      {
        title: '下月应付金额', dataIndex: 'next_month_due', width: 160, align: 'right' as const,
        sorter: true, sortOrder: getSortOrder('next_month_due'),
        render: (_: unknown, record: SupplierPaymentRow) => {
          const v = record.next_month_due
          if (v == null) return <span style={{ color: '#cbd5e1' }}>-</span>
          const monthLabel = record.next_month
            ? dayjs(record.next_month).isValid() ? dayjs(record.next_month).format('YYYY年M月') : record.next_month
            : ''
          return (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: 'monospace', fontWeight: 500 }}>{v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
              <div style={{ fontSize: '11px', color: '#94a3b8' }}>{monthLabel}</div>
            </div>
          )
        },
      },
```

3. `scroll={{ x: 1160 }}` 改为 `scroll={{ x: 1320 }}`。

**验证**：`cd frontend && npm run build` 通过。

---

## Task 6: 单元测试

**文件**: `backend/tests/unit/test_supplier_payment_next_month.py`（新文件）：

```python
"""下月应付金额计算单测（无 DB）。"""

from datetime import date
from decimal import Decimal

from app.services.material.supplier_payment_service import _compute_next_month_due


def _inv(invoice_date=None, term=None, remain='100', paid=0, order_id=None, apply_date=None):
    return {
        'invoice_date': invoice_date,
        'payment_term': term,
        'remain_payable': Decimal(remain),
        'paid_amount': Decimal(paid),
        'payment_order_id': order_id,
        'payment_apply_date': apply_date,
    }


def test_progress_month_next_month():
    # 进度月 2026-08；10月有应付、11月也有 → 取 10月
    invs = [
        _inv(date(2026, 9, 1), '30天', apply_date=date(2026, 8, 10)),   # 排款月 2026-10
        _inv(date(2026, 10, 20), '30天', apply_date=date(2026, 8, 5)),  # 排款月 2026-11
    ]
    assert _compute_next_month_due(invs) == ('2026-10', Decimal('100'))


def test_skip_empty_month():
    # 进度月 2026-07；8月已全付（有效应付0），9月有应付 → 9月
    invs = [
        _inv(date(2026, 8, 1), '30天', remain='100', paid=100, apply_date=date(2026, 7, 20)),  # 排款月 2026-08 全付
        _inv(date(2026, 8, 20), '30天', apply_date=date(2026, 7, 20)),  # 排款月 2026-09
    ]
    assert _compute_next_month_due(invs) == ('2026-09', Decimal('100'))


def test_no_apply_falls_back_earliest():
    # 无付款申请记录 → 最早应付月
    invs = [
        _inv(date(2026, 5, 1), '30天'),  # 排款月 2026-05
        _inv(date(2026, 4, 1), '30天'),  # 排款月 2026-05
    ]
    assert _compute_next_month_due(invs) == ('2026-05', Decimal('200'))


def test_all_paid_after_progress_returns_none():
    # 进度月之后全空 → None
    invs = [_inv(date(2026, 7, 1), '30天', remain='100', paid=100, apply_date=date(2026, 8, 1))]
    assert _compute_next_month_due(invs) == (None, None)


def test_in_transit_not_counted():
    # 在途票据（payment_order_id>0 未付）有效应付为0，跳过该月
    invs = [
        _inv(date(2026, 9, 1), '30天', order_id=5, apply_date=date(2026, 7, 1)),
        _inv(date(2026, 10, 1), '30天', apply_date=date(2026, 7, 1)),
    ]
    assert _compute_next_month_due(invs) == ('2026-10', Decimal('100'))


def test_no_invoice_date_skipped():
    invs = [_inv(None, '30天')]
    assert _compute_next_month_due(invs) == (None, None)
```

**验证**：`cd backend && python -m pytest tests/unit/test_supplier_payment_next_month.py -q` 全绿。

---

## Task 7: 全量校验 + 手动验证 + 提交

1. `cd backend && python -m pytest -q`（全量）。
2. `cd frontend && npm run build`。
3. 手动：容器内跑一次性脚本更新同步 SQL；触发 `POST /api/v1/basicdata/sync/purchase_invoices`（或等定时同步）回填 `payment_apply_date`；登录前端检查「下月应付金额」列、月份标注、排序、导出两列。
4. 删除一次性脚本；提交代码（commit message：`feat(supplier-payment): 排程新增下月应付金额列`）。
