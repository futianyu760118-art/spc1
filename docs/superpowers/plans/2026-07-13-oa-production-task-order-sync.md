# OA 生产任务单同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新建 `production_task_order` 表，从 OA 系统直连数据库同步生产任务单数据，并通过 `/api/v1/external` 暴露给外部系统。

**Architecture:** 复用现有 ERP 同步框架（`sync_sql_config` 表 + `ErpSyncService._bulk_upsert`）。新建 SQLAlchemy 模型 `ProductionTaskOrder`，新增 `sync_production_task_orders` 方法，种子 `SyncSqlConfig(sync_type="production_task_orders")`。对外通过 `data_supply_registry` 注册 + 新建 `external/endpoints/production_task_orders.py` 暴露。

**Tech Stack:** FastAPI + SQLAlchemy 2.x async + asyncpg, Pydantic v2, Alembic, PostgreSQL.

## Global Constraints

- TypeScript strict mode. `npm run build` (tsc -b && vite build) is the only typecheck; no lint/test/format scripts exist.
- App code uses async SQLAlchemy via `get_db()` which auto-commits/rolls-back — don't commit manually inside endpoints.
- Response envelope `{code, message, data}` is mandatory on all backend responses.
- DB migration rule: register schema changes in BOTH `init_database.py` AND a new Alembic revision. `init_database.py` is the runtime source of truth (runs on every container start).
- `init_database.py` `migrate_columns` is for `ADD COLUMN IF NOT EXISTS` only — brand-new tables are handled by `Base.metadata.create_all` (called from `init_database.py::create_tables`).
- No comments added to code unless asked.
- Backend: Python 3.12; Frontend: Node 20 (no frontend changes for this feature).
- Alembic down_revision: current head is `rename_scm_material_erp_id` (2026-07-13).

---

## Task 1: Create `ProductionTaskOrder` SQLAlchemy model

**Files:**
- `backend/app/models/production/production_task_order.py` (new)

**Step 1:** Create the model file with the exact content below.

```python
"""生产协同中心 — OA 生产任务单模型（同步自 OA 系统）"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Index, text
from sqlalchemy.sql import func

from app.core.database import Base


class ProductionTaskOrder(Base):
    __tablename__ = "production_task_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=True, comment="OA 任务单ID")
    task_no = Column(String(64), nullable=True, comment="任务单号")
    workshop = Column(String(128), nullable=True, comment="生产车间")
    material_code = Column(String(64), nullable=True, comment="物料代码")
    material_name = Column(String(256), nullable=True, comment="物料名称")
    planned_start_date = Column(Date, nullable=True, comment="计划开工日期")
    planned_end_date = Column(Date, nullable=True, comment="计划完工日期")
    actual_start_date = Column(Date, nullable=True, comment="实际开工日期")
    actual_end_date = Column(Date, nullable=True, comment="实际完工日期")
    task_qty = Column(Numeric(15, 2), nullable=True, comment="任务单数量")
    repair_qty = Column(Numeric(15, 2), nullable=True, comment="返修数量")
    actual_qty = Column(Numeric(15, 2), nullable=True, comment="实做数量")
    task_type = Column(String(64), nullable=True, comment="类型")
    sale_order_no = Column(String(64), nullable=True, comment="销售订单号")
    start_flag = Column(Integer, nullable=True, comment="开工标志 0/1")
    is_closed = Column(Integer, nullable=True, comment="是否关闭 0-未关闭 1-已关闭")
    audit_status = Column(Integer, nullable=True, comment="审核状态 0-未审核 1-已审核")
    mrp_flag = Column(Integer, nullable=True, comment="MRP标志 0/1")
    audit_user_id = Column(Integer, nullable=True, comment="审核人ID")
    request_user_id = Column(Integer, nullable=True, comment="请求人ID")
    supplier_id = Column(Integer, nullable=True, comment="供应商ID")

    data_source = Column(String(32), nullable=False, server_default="oa", default="oa", comment="数据来源")
    erp_updated_at = Column(DateTime, nullable=True, comment="OA端更新时间(用于增量同步)")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_production_task_order_task_id", "task_id", unique=True, postgresql_where=text("task_id IS NOT NULL")),
        Index("ix_production_task_order_task_no", "task_no"),
        Index("ix_production_task_order_material_code", "material_code"),
        Index("ix_production_task_order_sale_order_no", "sale_order_no"),
    )
```

**Step 2:** Verify the model imports.

```bash
cd backend && python -c "from app.models.production.production_task_order import ProductionTaskOrder; print(ProductionTaskOrder.__tablename__); print([c.name for c in ProductionTaskOrder.__table__.columns])"
```

Expected output: starts with `production_task_order` then column list including `id, task_id, task_no, ..., updated_at`.

---

## Task 2: Register model in `app/models/production/__init__.py`

**Files:**
- `backend/app/models/production/__init__.py`

**Step 1:** Append a new import line at the end of the file (after the existing `UpphFormulaConfig` import):

```python
from app.models.production.production_task_order import ProductionTaskOrder  # noqa: F401
```

**Step 2:** Verify.

```bash
cd backend && python -c "from app.models import production; from app.models.production import ProductionTaskOrder; print('OK')"
```

Expected output: `OK`

---

## Task 3: Create Alembic migration

**Files:**
- `backend/alembic/versions/add_production_task_order_table.py` (new)

**Step 1:** Create the migration file with the exact content below.

```python
"""add production_task_order table

Revision ID: add_production_task_order
Revises: rename_scm_material_erp_id
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_production_task_order"
down_revision: Union[str, None] = "rename_scm_material_erp_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_task_order",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), nullable=True, comment="OA 任务单ID"),
        sa.Column("task_no", sa.String(length=64), nullable=True, comment="任务单号"),
        sa.Column("workshop", sa.String(length=128), nullable=True, comment="生产车间"),
        sa.Column("material_code", sa.String(length=64), nullable=True, comment="物料代码"),
        sa.Column("material_name", sa.String(length=256), nullable=True, comment="物料名称"),
        sa.Column("planned_start_date", sa.Date(), nullable=True, comment="计划开工日期"),
        sa.Column("planned_end_date", sa.Date(), nullable=True, comment="计划完工日期"),
        sa.Column("actual_start_date", sa.Date(), nullable=True, comment="实际开工日期"),
        sa.Column("actual_end_date", sa.Date(), nullable=True, comment="实际完工日期"),
        sa.Column("task_qty", sa.Numeric(precision=15, scale=2), nullable=True, comment="任务单数量"),
        sa.Column("repair_qty", sa.Numeric(precision=15, scale=2), nullable=True, comment="返修数量"),
        sa.Column("actual_qty", sa.Numeric(precision=15, scale=2), nullable=True, comment="实做数量"),
        sa.Column("task_type", sa.String(length=64), nullable=True, comment="类型"),
        sa.Column("sale_order_no", sa.String(length=64), nullable=True, comment="销售订单号"),
        sa.Column("start_flag", sa.Integer(), nullable=True, comment="开工标志 0/1"),
        sa.Column("is_closed", sa.Integer(), nullable=True, comment="是否关闭"),
        sa.Column("audit_status", sa.Integer(), nullable=True, comment="审核状态 0-未审核 1-已审核"),
        sa.Column("mrp_flag", sa.Integer(), nullable=True, comment="MRP标志 0/1"),
        sa.Column("audit_user_id", sa.Integer(), nullable=True, comment="审核人ID"),
        sa.Column("request_user_id", sa.Integer(), nullable=True, comment="请求人ID"),
        sa.Column("supplier_id", sa.Integer(), nullable=True, comment="供应商ID"),
        sa.Column("data_source", sa.String(length=32), nullable=False, server_default="oa", comment="数据来源"),
        sa.Column("erp_updated_at", sa.DateTime(), nullable=True, comment="OA端更新时间"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_production_task_order_task_id ON production_task_order (task_id) WHERE task_id IS NOT NULL")
    op.create_index("ix_production_task_order_task_no", "production_task_order", ["task_no"])
    op.create_index("ix_production_task_order_material_code", "production_task_order", ["material_code"])
    op.create_index("ix_production_task_order_sale_order_no", "production_task_order", ["sale_order_no"])


def downgrade() -> None:
    op.drop_index("ix_production_task_order_sale_order_no", table_name="production_task_order")
    op.drop_index("ix_production_task_order_material_code", table_name="production_task_order")
    op.drop_index("ix_production_task_order_task_no", table_name="production_task_order")
    op.execute("DROP INDEX IF EXISTS uq_production_task_order_task_id")
    op.drop_table("production_task_order")
```

**Step 2:** Verify the migration file imports without errors (this catches syntax issues without touching the DB).

```bash
cd backend && python -c "import importlib.util, sys; spec = importlib.util.spec_from_file_location('m', 'alembic/versions/add_production_task_order_table.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('revision:', m.revision, 'down_revision:', m.down_revision)"
```

Expected output: `revision: add_production_task_order down_revision: rename_scm_material_erp_id`

---

## Task 4: Update `init_database.py` — import + seed SyncSqlConfig

**Files:**
- `backend/init_database.py`

**Step 1:** Add model import. In the `from app.models.production...` block (around line 32-34), add a new import line:

```python
from app.models.production.production_task_order import ProductionTaskOrder
```

**Step 2:** Append a new `SyncSqlConfig` entry. Locate the existing `SyncSqlConfig(sync_type="mrp_plan_orders", ...)` block (it ends with `created_by="admin",` followed by `),`). Right after that block's closing `),`, add the following new entry:

```python
                    SyncSqlConfig(
                        sync_type="production_task_orders",
                        description="OA 生产任务单 — 从OA数据库 oa_production_task 表拉取（占位SQL，部署时需根据实际表名/字段调整）",
                        sql_text="""
SELECT
    CAST(FID AS INT)                       AS task_id,
    CAST(FBillNo AS VARCHAR(64))           AS task_no,
    CAST(FWorkShop AS VARCHAR(128))        AS workshop,
    CAST(FMaterialCode AS VARCHAR(64))     AS material_code,
    CAST(FMaterialName AS VARCHAR(256))    AS material_name,
    CAST(FPlanStartDate AS DATE)           AS planned_start_date,
    CAST(FPlanEndDate AS DATE)             AS planned_end_date,
    CAST(FActualStartDate AS DATE)         AS actual_start_date,
    CAST(FActualEndDate AS DATE)           AS actual_end_date,
    CAST(FQty AS DECIMAL(15,2))            AS task_qty,
    CAST(FRepairQty AS DECIMAL(15,2))      AS repair_qty,
    CAST(FActualQty AS DECIMAL(15,2))      AS actual_qty,
    CAST(FType AS VARCHAR(64))             AS task_type,
    CAST(FSaleOrderNo AS VARCHAR(64))      AS sale_order_no,
    CAST(FStartFlag AS INT)                AS start_flag,
    CAST(FClosed AS INT)                   AS is_closed,
    CAST(FStatus AS INT)                   AS audit_status,
    CAST(FMrpFlag AS INT)                  AS mrp_flag,
    CAST(FAuditUserId AS INT)              AS audit_user_id,
    CAST(FRequestUserId AS INT)            AS request_user_id,
    CAST(FSupplierId AS INT)               AS supplier_id,
    FModifyDate                            AS erp_updated_at
FROM oa_production_task
WHERE FModifyDate >= :since
ORDER BY FModifyDate DESC
                        """.strip(),
                        field_mapping_json=None,
                        sync_interval="1h",
                        sync_strategy="incremental",
                        sync_priority=5,
                        is_active=True,
                        sync_enabled=True,
                        created_by="admin",
                    ),
```

**Step 3:** Verify the file still parses.

```bash
cd backend && python -c "import ast; ast.parse(open('init_database.py', encoding='utf-8').read()); print('OK')"
```

Expected output: `OK`

---

## Task 5: Update `erp_sync_service.py` — import + sync method + sync_all

**Files:**
- `backend/app/services/basicdata/erp_sync_service.py`

**Step 1:** Add import. After `from app.models.material.mrp_plan_order import MrpPlanOrder` (line 41), add:

```python
from app.models.production.production_task_order import ProductionTaskOrder
```

**Step 2:** Add the sync method. Right after the `sync_mrp_plan_orders` method (which ends with the `return stats` at line 2699), insert this new method:

```python
    async def sync_production_task_orders(
        self, since: Optional[datetime] = None, custom_params: Optional[dict] = None
    ) -> dict:
        """同步 OA 生产任务单数据。幂等依据: task_id 唯一。"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("production_task_orders")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 OA/ERP 获取到 {len(rows)} 条生产任务单记录")

            stats = await self._bulk_upsert(
                ProductionTaskOrder,
                rows,
                mapping,
                key_fields=["task_id"],
                label="生产任务单",
            )

            await self.spc_db.flush()
            await self.spc_db.commit()
            logger.info(f"生产任务单同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"生产任务单同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats
```

**Step 3:** Add to `sync_all`. Locate the line `results["mrp_plan_orders"] = await self.sync_mrp_plan_orders(since, custom_params)` in the `sync_all` method and add right after it:

```python
            results["production_task_orders"] = await self.sync_production_task_orders(since, custom_params)
```

**Step 4:** Verify the file still parses and the method is importable.

```bash
cd backend && python -c "import ast; ast.parse(open('app/services/basicdata/erp_sync_service.py', encoding='utf-8').read()); print('OK')"
```

Expected output: `OK`

---

## Task 6: Update `sync.py` — register `production_task_orders` in `VALID_SYNC_TYPES` and `type_map`

**Files:**
- `backend/app/api/v1/basicdata/sync.py`

**Step 1:** Update `VALID_SYNC_TYPES`. In the `VALID_SYNC_TYPES` list (line 31-35), add `"production_task_orders"` right after `"mrp_plan_orders"`:

```python
VALID_SYNC_TYPES = [
    "orders", "order_details", "materials", "purchase_orders", "customers", "suppliers",
    "materials_masterdata", "skus", "products", "boms", "bom_details", "warehouses", "locations", "processes",
    "organizations", "positions", "employees", "employee_organizations", "purchase_invoices", "payment_applies", "quality_issues", "mrp_plan_orders", "production_task_orders", "inventory", "all",
]
```

**Step 2:** Add handler in `type_map`. Right after the `"mrp_plan_orders": lambda: service.sync_mrp_plan_orders(...)` entry (line 95), add:

```python
                "production_task_orders": lambda: service.sync_production_task_orders(
                    sync_params.get("since"), custom_params
                ),
```

**Step 3:** Verify.

```bash
cd backend && python -c "import ast; ast.parse(open('app/api/v1/basicdata/sync.py', encoding='utf-8').read()); print('OK')"
```

Expected output: `OK`

---

## Task 7: Update `sync_scheduler.py` — register scheduler type

**Files:**
- `backend/app/services/basicdata/sync_scheduler.py`

**Step 1:** Add the new entry in the scheduler's type_map (around line 53). Right after `"mrp_plan_orders": "sync_mrp_plan_orders",` add:

```python
            "production_task_orders": "sync_production_task_orders",
```

**Step 2:** Verify.

```bash
cd backend && python -c "import ast; ast.parse(open('app/services/basicdata/sync_scheduler.py', encoding='utf-8').read()); print('OK')"
```

Expected output: `OK`

---

## Task 8: Register `production_task_orders` in `data_supply_registry.py`

**Files:**
- `backend/app/services/basicdata/data_supply_registry.py`

**Step 1:** Append a new `register_data_type(...)` block at the end of the file (right before any trailing blank line). Copy this exactly:

```python
register_data_type(DataTypeDefinition(
    data_type="production_task_orders",
    data_name="生产任务单",
    description="OA 生产任务单（车间作业级）",
    model_name="ProductionTaskOrder",
    exposed_fields=[
        "id", "task_id", "task_no", "workshop",
        "material_code", "material_name",
        "planned_start_date", "planned_end_date",
        "actual_start_date", "actual_end_date",
        "task_qty", "repair_qty", "actual_qty",
        "task_type", "sale_order_no",
        "start_flag", "is_closed", "audit_status", "mrp_flag",
        "audit_user_id", "request_user_id", "supplier_id",
        "erp_updated_at", "updated_at",
    ],
    filter_fields=["workshop", "task_type", "is_closed", "audit_status", "mrp_flag", "sale_order_no"],
    search_fields=["task_no", "material_name"],
))
```

**Step 2:** Verify.

```bash
cd backend && python -c "from app.services.basicdata.data_supply_registry import DATA_TYPE_REGISTRY, get_data_type_definition; d = get_data_type_definition('production_task_orders'); print(d.data_name, d.model_name, len(d.exposed_fields))"
```

Expected output: `生产任务单 ProductionTaskOrder 24` (24 fields; may be `23` if I miscounted — verify the count matches `len(exposed_fields)`, the exact number is not critical).

---

## Task 9: Create external endpoint for `production_task_orders`

**Files:**
- `backend/app/api/v1/external/endpoints/production_task_orders.py` (new)

**Step 1:** Create the endpoint file with the exact content below. Pattern follows `external/endpoints/production.py::schedule_plans_list`.

```python
"""生产任务单对外接口

为外部系统定制的 OA 生产任务单查询接口。基于 ProductionTaskOrder 表。
支持分页、关键字、车间、类型、状态、增量同步。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.production.production_task_order import ProductionTaskOrder

from ..registry import register_external, ExternalCallContext


def _parse_int(s: Optional[str]) -> Optional[int]:
    if s is None or s == "":
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@register_external(
    "production_task_orders.list",
    "生产任务单列表",
    method="GET",
    path="/production-task-orders/list",
    description="OA 生产任务单列表查询，支持关键字、车间、类型、状态、增量同步",
    tags=["生产"],
)
async def production_task_orders_list(ctx: ExternalCallContext) -> dict:
    """生产任务单列表（外部定制版）

    参数（query）：
        page, page_size: 分页
        keyword: 关键字（任务单号 / 物料名称 模糊匹配）
        workshop: 生产车间精确匹配
        task_type: 类型精确匹配
        is_closed: 是否关闭 0/1
        audit_status: 审核状态 0=未审核 1=已审核
        mrp_flag: MRP标志 0/1
        sale_order_no: 销售订单号精确匹配
        updated_after: 增量同步，仅返回 updated_at >= 此时间的记录 (ISO 8601)
    """
    params = ctx.params
    db = ctx.db

    page = max(int(params.get("page", 1) or 1), 1)
    page_size = min(max(int(params.get("page_size", 20) or 20), 1), 200)
    keyword = params.get("keyword")
    workshop = params.get("workshop")
    task_type = params.get("task_type")
    is_closed = _parse_int(params.get("is_closed"))
    audit_status = _parse_int(params.get("audit_status"))
    mrp_flag = _parse_int(params.get("mrp_flag"))
    sale_order_no = params.get("sale_order_no")
    updated_after = _parse_dt(params.get("updated_after"))

    query = select(ProductionTaskOrder)
    count_query = select(func.count()).select_from(ProductionTaskOrder)

    if keyword:
        like_expr = f"%{keyword}%"
        kw_cond = or_(
            ProductionTaskOrder.task_no.ilike(like_expr),
            ProductionTaskOrder.material_name.ilike(like_expr),
        )
        query = query.where(kw_cond)
        count_query = count_query.where(kw_cond)

    if workshop:
        query = query.where(ProductionTaskOrder.workshop == workshop)
        count_query = count_query.where(ProductionTaskOrder.workshop == workshop)

    if task_type:
        query = query.where(ProductionTaskOrder.task_type == task_type)
        count_query = count_query.where(ProductionTaskOrder.task_type == task_type)

    if is_closed is not None:
        query = query.where(ProductionTaskOrder.is_closed == is_closed)
        count_query = count_query.where(ProductionTaskOrder.is_closed == is_closed)

    if audit_status is not None:
        query = query.where(ProductionTaskOrder.audit_status == audit_status)
        count_query = count_query.where(ProductionTaskOrder.audit_status == audit_status)

    if mrp_flag is not None:
        query = query.where(ProductionTaskOrder.mrp_flag == mrp_flag)
        count_query = count_query.where(ProductionTaskOrder.mrp_flag == mrp_flag)

    if sale_order_no:
        query = query.where(ProductionTaskOrder.sale_order_no == sale_order_no)
        count_query = count_query.where(ProductionTaskOrder.sale_order_no == sale_order_no)

    if updated_after:
        query = query.where(ProductionTaskOrder.updated_at >= updated_after)
        count_query = count_query.where(ProductionTaskOrder.updated_at >= updated_after)

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(ProductionTaskOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    items = [{
        "id": r.id,
        "task_id": r.task_id,
        "task_no": r.task_no,
        "workshop": r.workshop,
        "material_code": r.material_code,
        "material_name": r.material_name,
        "planned_start_date": r.planned_start_date.isoformat() if r.planned_start_date else None,
        "planned_end_date": r.planned_end_date.isoformat() if r.planned_end_date else None,
        "actual_start_date": r.actual_start_date.isoformat() if r.actual_start_date else None,
        "actual_end_date": r.actual_end_date.isoformat() if r.actual_end_date else None,
        "task_qty": float(r.task_qty) if r.task_qty is not None else None,
        "repair_qty": float(r.repair_qty) if r.repair_qty is not None else None,
        "actual_qty": float(r.actual_qty) if r.actual_qty is not None else None,
        "task_type": r.task_type,
        "sale_order_no": r.sale_order_no,
        "start_flag": r.start_flag,
        "is_closed": r.is_closed,
        "audit_status": r.audit_status,
        "mrp_flag": r.mrp_flag,
        "audit_user_id": r.audit_user_id,
        "request_user_id": r.request_user_id,
        "supplier_id": r.supplier_id,
        "erp_updated_at": r.erp_updated_at.isoformat() if r.erp_updated_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
```

**Step 2:** Verify the file parses.

```bash
cd backend && python -c "import ast; ast.parse(open('app/api/v1/external/endpoints/production_task_orders.py', encoding='utf-8').read()); print('OK')"
```

Expected output: `OK`

---

## Task 10: Register endpoint module in `external/endpoints/__init__.py`

**Files:**
- `backend/app/api/v1/external/endpoints/__init__.py`

**Step 1:** Add an import line. Append the following after the `from . import warehouse` line:

```python
from . import production_task_orders  # noqa: F401
```

**Step 2:** Verify the endpoint is registered.

```bash
cd backend && python -c "from app.api.v1.external.endpoints import production_task_orders; from app.api.v1.external.registry import get_endpoint_by_code; e = get_endpoint_by_code('production_task_orders.list'); print(e.name, e.path)"
```

Expected output: `生产任务单列表 /production-task-orders/list`

---

## Task 11: Final verification — server starts and endpoint reachable

**Step 1:** Boot the backend and verify the model registers without error.

```bash
cd backend && python -c "from app.main import app; from app.models.production.production_task_order import ProductionTaskOrder; print('routes count:', len(app.routes))"
```

Expected output: ends with `routes count: <some positive number>`. No traceback.

**Step 2:** Run init_database.py (idempotency check). If the dev DB is running, this is the most important end-to-end check.

```bash
cd backend && python init_database.py
```

Expected output: ends with `数据库初始化完成` (or similar) and no traceback. The `create_all` will create the new `production_task_order` table.

**Step 3:** Verify the new table exists in DB.

```bash
cd backend && python -c "
import asyncio
from app.core.database import engine
from sqlalchemy import text

async def check():
    async with engine.begin() as conn:
        r = await conn.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name = 'production_task_order' ORDER BY ordinal_position\"))
        cols = [row[0] for row in r.fetchall()]
        print('table exists, columns:', cols)
        assert 'task_id' in cols and 'data_source' in cols
        print('OK')
asyncio.run(check())
"
```

Expected output: `table exists, columns: [...]` ending with `OK`. (Column list should contain `id, task_id, task_no, workshop, material_code, material_name, planned_start_date, planned_end_date, actual_start_date, actual_end_date, task_qty, repair_qty, actual_qty, task_type, sale_order_no, start_flag, is_closed, audit_status, mrp_flag, audit_user_id, request_user_id, supplier_id, data_source, erp_updated_at, created_at, updated_at`.)

**Step 4:** Verify the SyncSqlConfig seed is present.

```bash
cd backend && python -c "
import asyncio
from app.core.database import AsyncSessionLocal
from app.models.basicdata.sync_sql_config import SyncSqlConfig
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(SyncSqlConfig).where(SyncSqlConfig.sync_type == 'production_task_orders'))
        c = r.scalar_one_or_none()
        if c:
            print('seed exists, interval:', c.sync_interval, 'strategy:', c.sync_strategy, 'enabled:', c.sync_enabled)
        else:
            print('SEED MISSING — run init_database.py first')

asyncio.run(check())
"
```

Expected output: `seed exists, interval: 1h strategy: incremental enabled: True` (if the DB has been initialized). Otherwise `SEED MISSING` — run `python init_database.py` first.

**Step 5:** TypeScript build (sanity check, no frontend changes expected).

```bash
cd frontend && npm run build
```

Expected output: builds successfully.

---

## Task 12: Commit

**Step 1:** Stage and commit all new and modified files.

```bash
git add \
  backend/app/models/production/production_task_order.py \
  backend/app/models/production/__init__.py \
  backend/alembic/versions/add_production_task_order_table.py \
  backend/init_database.py \
  backend/app/services/basicdata/erp_sync_service.py \
  backend/app/api/v1/basicdata/sync.py \
  backend/app/services/basicdata/sync_scheduler.py \
  backend/app/services/basicdata/data_supply_registry.py \
  backend/app/api/v1/external/endpoints/production_task_orders.py \
  backend/app/api/v1/external/endpoints/__init__.py
git status
git commit -m "feat(production): 同步OA生产任务单数据 + 暴露对外接口"
```

Expected output: commit succeeds, `git status` shows clean working tree (other than pre-existing modifications from other work-in-progress features).

---

## Notes for the implementer

- **OA 真实表名/字段待确认**：`init_database.py` 里种子的 SQL 是占位符（参考 K3 `F*` 风格 + 表名 `oa_production_task`）。部署到生产前需要在「同步SQL配置」页面替换为真实 SQL。
- **无测试框架**：本仓库 `backend/test_*.py` 是手写脚本（AGENTS.md），不是 pytest。本 plan 的"验证"步骤是手动 smoke test，不写自动化测试。
- **历史回填**：`POST /api/v1/import-export/sync/production_task_orders?hours=720` 可以拉 30 天窗口历史数据。
