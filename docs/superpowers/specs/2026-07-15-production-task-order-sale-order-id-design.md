# Design: `ProductionTaskOrder` 新增 `sale_order_id` 销售订单外键

**Date:** 2026-07-15
**Status:** Approved (pending review)
**Author:** opencode

## Background

`production_task_order` 表（OA 同步的生产任务单）目前仅通过字符串列 `sale_order_no`（销售订单号，VARCHAR(64)）与 `sale_order` 表做隐式关联，无数据库外键、无 ORM 关系。报表/查询侧需要按销售订单整数 ID 关联时只能通过 `sale_order_no` 字符串匹配，效率低且无强一致保证。

`SaleOrder` 表（`sale_order`）的整数主键为 `id`，业务唯一键为 `(order_no, line_no)`。本设计在 `production_task_order` 上新增一个真正的整数外键列 `sale_order_id → sale_order.id`，使跨表 JOIN 可走索引、跨表一致性由 DB 约束保证。

## Goals

- 让 `ProductionTaskOrder` 可以用整数外键 `sale_order_id` 直接 JOIN `sale_order`。
- 不破坏现有数据流：`sale_order_no`（String）保留。
- 历史数据**不**回填：新列允许 NULL。
- **不**改 OA 同步逻辑（`erp_sync_service.py::sync_production_task_orders`）。

## Non-Goals

- 改 OA 同步 SQL/字段映射（明确不做）。
- 数据回填（明确不做）。
- 删除或废弃 `sale_order_no`（明确不做）。
- 在 SQLAlchemy 模型上加 `relationship('SaleOrder')`（避免跨域 lazy-load）。
- 新增 Pydantic schema（当前无此模型对应的 schema）。

## Design

### 1. 模型变更 — `backend/app/models/production/production_task_order.py`

在 `sale_order_no` 列**之后**新增 `sale_order_id` 列，并加入 `__table_args__` 索引：

```python
sale_order_no = Column(String(64), nullable=True, comment="销售订单号")
sale_order_id = Column(Integer, ForeignKey("sale_order.id"), nullable=True, comment="销售订单ID")
```

`__table_args__` 追加索引：

```python
Index("ix_production_task_order_sale_order_id", "sale_order_id"),
```

注意：`import` 列表需要加入 `ForeignKey`（当前文件 imports 是 `from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Index, text`）。

### 2. 运行时迁移 — `backend/init_database.py`

在 `migrate_columns()` 函数的 `new_columns` 字典中**新增** `production_task_order` 表项（当前不存在，必须**首次**加入）：

```python
"production_task_order": {
    "sale_order_id": "INTEGER",
},
```

位置：紧跟在 `"purchase_order":` 之后（按字母顺序排列的当前惯例之前），实际是新增 key；建议放在 `"process_progress":` 之后（字母 p 区段内）。

执行 SQL 等价于：
```sql
ALTER TABLE production_task_order ADD COLUMN IF NOT EXISTS sale_order_id INTEGER;
```

无 `NOT NULL`、无 `REFERENCES` 字句 —— FK 由 SQLAlchemy 模型声明，PostgreSQL 的 `create_all` 会在新装环境上补上 FK 约束；既有环境若缺 FK，可由 Alembic 迁移补。

### 3. Alembic 迁移 — `backend/alembic/versions/<new>_add_production_task_order_sale_order_id.py`

新建迁移文件，`down_revision = "add_production_task_order"`：

```python
"""add production_task_order.sale_order_id

Revision ID: add_production_task_order_sale_order_id
Revises: add_production_task_order
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_production_task_order_sale_order_id"
down_revision: Union[str, None] = "add_production_task_order"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "production_task_order",
        sa.Column("sale_order_id", sa.Integer(), nullable=True, comment="销售订单ID"),
    )
    op.create_index(
        "ix_production_task_order_sale_order_id",
        "production_task_order",
        ["sale_order_id"],
    )
    op.create_foreign_key(
        "fk_production_task_order_sale_order_id",
        "production_task_order",
        "sale_order",
        ["sale_order_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_production_task_order_sale_order_id",
        "production_task_order",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_production_task_order_sale_order_id",
        table_name="production_task_order",
    )
    op.drop_column("production_task_order", "sale_order_id")
```

### 4. 数据供给注册 — `backend/app/services/basicdata/data_supply_registry.py`

第 297-307 行 `exposed_fields` 列表追加 `"sale_order_id"`：

```python
exposed_fields=[
    "id", "task_id", "task_no", "workshop",
    "material_code", "material_name",
    "planned_start_date", "planned_end_date",
    "actual_start_date", "actual_end_date",
    "task_qty", "repair_qty", "actual_qty",
    "task_type", "sale_order_no", "sale_order_id",
    "start_flag", "is_closed", "audit_status", "mrp_flag",
    "audit_user_id", "request_user_id", "supplier_id",
    "erp_updated_at", "updated_at",
],
```

`filter_fields` / `search_fields` **不**改（保持现状，避免破坏外部调用方预期）。

### 5. 外部接口 — `backend/app/api/v1/external/endpoints/production_task_orders.py`

第 119-144 行 `items` 字典构造中追加 `"sale_order_id": r.sale_order_id`（紧跟 `sale_order_no` 后）。

docstring 第 53 行的参数说明**不**改（仅 `sale_order_no` 即可作为入参过滤，新列只读）。

## Files Changed

| # | File | 改动类型 |
|---|------|---------|
| 1 | `backend/app/models/production/production_task_order.py` | import + 列 + 索引 |
| 2 | `backend/init_database.py` | 新增 `production_task_order` 到 `new_columns` |
| 3 | `backend/alembic/versions/<rev>_add_production_task_order_sale_order_id.py` | 新文件 |
| 4 | `backend/app/services/basicdata/data_supply_registry.py` | `exposed_fields` 加一项 |
| 5 | `backend/app/api/v1/external/endpoints/production_task_orders.py` | `items` 字典加一项 |

## Risks & Trade-offs

- **数据冗余 / 不一致风险**：`sale_order_no` 与 `sale_order_id` 同一行可能指向不同 `sale_order`（理论上）。本设计通过"不改同步、只读侧关联"控制——`sale_order_id` 初始全为 NULL，写入路径仅限人工/报表补录。
- **可空 FK**：使用 `nullable=True` 而非 `NOT NULL` + 默认值；避免历史行导入失败、不影响既有数据。
- **索引策略**：单列 B-tree 索引，匹配"按销售订单 id 找所有生产任务单"的典型查询。
- **FK 约束时机**：Alembic 迁移显式建 FK；`init_database.py` 的 `ADD COLUMN IF NOT EXISTS` 不带 `REFERENCES`，因为 `ALTER TABLE ADD COLUMN ... REFERENCES` 在某些 PG 版本下与 `IF NOT EXISTS` 组合不可靠，由 Alembic 兜底。`create_all` 在新装环境也会自动建 FK。
- **No test suite**：本仓库无 pytest（见 AGENTS.md），改动通过 uvicorn 启动 + Alembic upgrade + 手动查询验证。

## Verification

1. `cd backend && alembic upgrade head` —— 应成功应用新迁移，无 FK 冲突。
2. `python init_database.py` —— 启动日志应有 `Column production_task_order.sale_order_id skipped` 或成功信息，无错误。
3. uvicorn 启动，`psql` 查询：
   - `\d production_task_order` —— 应见 `sale_order_id integer` 列 + 索引 + FK。
   - `SELECT count(*) FROM production_task_order WHERE sale_order_id IS NULL;` —— 应等于表总行数（无回填）。
4. `GET /api/v1/external/production-task-orders/list` —— 响应项中应包含 `sale_order_id` 字段。
5. `frontend npm run build` —— 不受影响（前端无 `ProductionTaskOrder` 模型）。

## Out of Scope

- 回填脚本（如需后续单独做，可加 `backend/once/backfill_production_task_order_sale_order_id.py`）
- 报表侧代码改动
- OA 端 SQL 更新
- 删除 `sale_order_no`
