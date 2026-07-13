# Design: OA 生产任务单同步（SPC `production_task_order`）

**Date:** 2026-07-13
**Status:** Draft, pending user approval
**Scope:** 新增 `production_task_order` 表，OA 系统生产任务单数据定时同步到 SPC，对外作为数据类型暴露，支持外部系统拉取。

---

## 1. Background

OA 系统自己维护了一张生产任务单表（任务单 id、单号、生产车间、物料、计划/实际日期、任务数量、状态、审核人/请求人/供应商 ID 等），用于车间作业排产与报工。

目前 SPC 系统已有的「生产任务单」相关数据来源只有 K3 ERP 的 `mrp_plan_order`（`bill_type = 11011` 表示自制生产任务单），与 OA 这张表是**不同系统、不同口径**的数据：

- `mrp_plan_order` 来自 K3 ERP `ICMrpResult` 表，结构是「销售订单 + 物料」组合，是 MRP 运算结果
- OA 的生产任务单是车间实际下发的任务（带「任务单号」、车间、实际开工/完工等车间现场字段）

用户需要把 OA 的数据也同步到 SPC，并提供对外访问（OA 或其他系统可调用 `/api/v1/external/...` 拉取）。

用户已确认：
1. 数据接入方式：OA 直连数据库（与现有 ERP 同步模式一致，复用 `sync_sql_config` + `erp_sync_service`）
2. 对外暴露：在 `data_supply_registry` 注册 `production_task_orders`，新建 `external/endpoints/production_task_orders.py` 端点
3. 数据库迁移：既改 `init_database.py`，也追加 Alembic 迁移
4. 字段以用户提供的 21 个字段为准（"按照我给的字段来就好"），不再额外加业务字段

---

## 2. Schema 设计

### 2.1 新表 `production_task_order`

**字段映射**（用户给的 OA 字段 → SPC 列名，沿用 codebase 现有命名习惯）：

| OA 字段 (中文) | SPC 列名 | 类型 | NULL | 备注 |
|---|---|---|---|---|
| 任务单id(int) | `task_id` | INTEGER | YES | OA 源主键，UNIQUE 索引（WHERE NOT NULL） |
| 任务单号 | `task_no` | VARCHAR(64) | YES | 业务编号 |
| 生产车间 | `workshop` | VARCHAR(128) | YES | |
| 物料代码 | `material_code` | VARCHAR(64) | YES | |
| 物料名称 | `material_name` | VARCHAR(256) | YES | |
| 计划开工日期 | `planned_start_date` | DATE | YES | |
| 计划完工日期 | `planned_end_date` | DATE | YES | |
| 实际开工日期 | `actual_start_date` | DATE | YES | |
| 实际完工日期 | `actual_end_date` | DATE | YES | |
| 任务单数量 | `task_qty` | NUMERIC(15,2) | YES | |
| 返修数量 | `repair_qty` | NUMERIC(15,2) | YES | |
| 实做数量 | `actual_qty` | NUMERIC(15,2) | YES | |
| 类型 | `task_type` | VARCHAR(64) | YES | 用 `task_type` 避开 SQL 关键字 `type` |
| 销售订单 | `sale_order_no` | VARCHAR(64) | YES | |
| 开工标志 | `start_flag` | INTEGER | YES | bool 风格 0/1 |
| 是否关闭(int) | `is_closed` | INTEGER | YES | 0-未关闭 1-已关闭 |
| 状态（0=未审核 1=已审核） | `audit_status` | INTEGER | YES | 用 `audit_status` 避免和通用 `status` 冲突 |
| MRP标志 | `mrp_flag` | INTEGER | YES | |
| 审核人id(int) | `audit_user_id` | INTEGER | YES | |
| 请求人id(int) | `request_user_id` | INTEGER | YES | |
| 供应商id(int) | `supplier_id` | INTEGER | YES | |

**框架必需的补充字段**（与现有 ERP 同步表保持一致）：

| 列名 | 类型 | 备注 |
|---|---|---|
| `id` | INTEGER PK, autoincrement | SPC 内部主键 |
| `data_source` | VARCHAR(32) NOT NULL DEFAULT 'oa' | 区分来源，遵循现有 `mrp_plan_order` 风格 |
| `erp_updated_at` | TIMESTAMP | OA 端 `modify_time` 映射，用于增量同步（`:since`） |
| `created_at` | TIMESTAMP NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMP NOT NULL DEFAULT now() on update now() | |

**索引：**
- `uq_production_task_order_task_id` UNIQUE INDEX on `task_id` WHERE `task_id IS NOT NULL`（与 `scm_employee.oa_user_id` 等已有模式一致）
- `ix_production_task_order_task_no` on `task_no`（业务查询）
- `ix_production_task_order_material_code` on `material_code`
- `ix_production_task_order_sale_order_no` on `sale_order_no`

### 2.2 不在范围内

- 不做去重/合并到 `mrp_plan_order`（两个系统口径不同，独立实体）
- 不改 `ProductionSchedulePlan` 或 `schedule_plan` 排产表
- 不实现状态机联动（`audit_status` / `is_closed` / `start_flag` 等只是同步存储，不触发业务动作）

---

## 3. 代码改动

### 3.1 新模型 `backend/app/models/production/production_task_order.py`

```python
"""生产协同中心 — OA 生产任务单模型（同步自 OA 系统）"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Index, text
from sqlalchemy.sql import func

from app.core.database import Base


class ProductionTaskOrder(Base):
    """OA 生产任务单 — 任务单同步存储表

    数据来源 OA 系统自身的生产任务单表（车间作业级，非 K3 MRP 结果）。
    同步方式：SPC 通过 sync_sql_config 配 SQL 直连 OA 数据库，task_id 唯一 upsert。
    """
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

需要在 `backend/app/models/production/__init__.py` 追加 import。

### 3.2 同步服务 `backend/app/services/basicdata/erp_sync_service.py`

新增方法（参考 `sync_mrp_plan_orders`）：

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

并在文件顶部追加 `from app.models.production.production_task_order import ProductionTaskOrder`。

在 `sync_all` 方法中追加 `results["production_task_orders"] = await self.sync_production_task_orders(since, custom_params)`。

### 3.3 init_database.py

1. 在导入区追加 `from app.models.production.production_task_order import ProductionTaskOrder`
2. 在种子 `SyncSqlConfig` 列表中追加一条（沿用 `mrp_plan_orders` 的 SQL 占位符风格）：

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

注：`create_all` 会自动建表（因为新模型在 `Base.metadata` 中），`migrate_columns` 主要是为已有表加列，新表不需要进 `migrate_columns`。但保险起见，新表的 UNIQUE 索引需要单独建（`create_all` 在 `Index` 对象上声明了 `unique=True` 和 `postgresql_where` 时会一并创建，无需手工）。

### 3.4 对外数据类型注册 `backend/app/services/basicdata/data_supply_registry.py`

追加：

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

### 3.5 对外接口 `backend/app/api/v1/external/endpoints/production_task_orders.py`

参考 `production.py::schedule_plans_list` 的写法。完整端点：`production_task_orders.list`，路径 `GET /external/production-task-orders/list`。

支持参数：
- `page`, `page_size` (分页)
- `keyword` (匹配 `task_no` / `material_name`)
- `workshop` (精确)
- `task_type` (精确)
- `is_closed` (0/1)
- `audit_status` (0/1)
- `mrp_flag` (0/1)
- `sale_order_no` (精确)
- `updated_after` (ISO8601, 增量同步)

并在 `backend/app/api/v1/external/endpoints/__init__.py` 追加 import（参考现有 `production` 的导入方式）。

### 3.6 Alembic 迁移

新文件 `backend/alembic/versions/add_production_task_order_table.py`：

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
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
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

`down_revision` 取当前最新 head：`rename_scm_material_erp_id`（2026-07-13）。

---

## 4. 涉及文件清单

| 序号 | 文件 | 改动 |
|---|---|---|
| 1 | `backend/app/models/production/production_task_order.py` | **新增** 模型 |
| 2 | `backend/app/models/production/__init__.py` | 追加 import |
| 3 | `backend/alembic/versions/add_production_task_order_table.py` | **新增** 迁移 |
| 4 | `backend/init_database.py` | 追加 import + SyncSqlConfig 种子 |
| 5 | `backend/app/services/basicdata/erp_sync_service.py` | 追加 `sync_production_task_orders` 方法 + `sync_all` 追加一行 |
| 6 | `backend/app/services/basicdata/data_supply_registry.py` | 注册 `production_task_orders` 数据类型 |
| 7 | `backend/app/api/v1/external/endpoints/production_task_orders.py` | **新增** 端点 |
| 8 | `backend/app/api/v1/external/endpoints/__init__.py` | 追加 import 触发装饰器注册 |

**无前端改动**（`data_supply_registry` 注册后，前端「系统配置 → 对外数据」会自动列出该数据类型；「同步SQL配置」页面会自动列出 `sync_type=production_task_orders` 配置）。

---

## 5. 验证方案

1. **模型可导入**：`cd backend && python -c "from app.models.production.production_task_order import ProductionTaskOrder; print(ProductionTaskOrder.__tablename__)"`
2. **Alembic 升级**：`alembic upgrade head`（或针对生产 head `rename_scm_material_erp_id`），通过 psql `\d production_task_order` 验证表结构
3. **init_database.py 幂等**：连续运行两次 `python init_database.py`，无报错
4. **同步可用**：
   - 启动 uvicorn
   - 用 `admin` 登录获取 token
   - 调 `POST /api/v1/import-export/sync/production_task_orders`（占位 SQL 会失败/返回空，但**接口存在并鉴权通过**即说明架子搭好）
   - 用户后续在「同步SQL配置」页面替换为真实 OA 表 SQL 后再测
5. **对外接口**：调 `GET /api/v1/external/production-task-orders/list`（需先创建 API Key，授予 `production_task_orders.list` 权限），验证分页/过滤/增量
6. **前端 build**：`cd frontend && npm run build`（按 AGENTS.md，无新 TS 代码，理论上无影响）

---

## 6. 风险 / 不在范围

- **OA 真实表名/字段未提供**：种子 SQL 用占位字段名（`F*` 前缀，参考金蝶 K3 风格）。部署到生产前必须由 OA 管理员确认表名（暂定 `oa_production_task`）和字段名，并在「同步SQL配置」页面更新为实际 SQL。
- **OA 任务单和 K3 MRP 结果可能重复**：本表与 `mrp_plan_order` 独立存在。如果后续要做交叉对比，需要单独建关系表。
- **同步频率**：`1h` 是默认，业务量大的话可在前端改成 `30m` 或 `15m`。
- **历史数据回填**：用户未要求。如果需要，调 `POST /api/v1/import-export/sync/production_task_orders?hours=720`（30 天窗口）。
- **供应商/员工 ID**：本表只存 int ID，不做 JOIN（OA 那边不一定是 SPC 自己的供应商/员工主数据）。后续要做关联再补。
