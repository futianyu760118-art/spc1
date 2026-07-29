"""add production_labor_price_audit table

Revision ID: add_labor_price_audit
Revises: add_pdr_oa_detail_id
Create Date: 2026-07-28

说明：
- 新增 production_labor_price_audit 表（工价审核数据，ERP 同步）。
- 业务主键 labor_price_code（工价表唯一码），partial unique index（NULL 不参与唯一约束）。
- 幂等：若表已由 init_database.py 的 Base.metadata.create_all 创建则跳过建表；
  索引一律 CREATE INDEX IF NOT EXISTS。与 init_database.py 并存不冲突。
  (项目以 init_database.py 为运行时真相源；Alembic 仅手动执行。)
- revision id ≤ 32 字符，规避 alembic_version.version_num 默认 varchar(32) 限制。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_labor_price_audit"
down_revision: Union[str, None] = "add_pdr_oa_detail_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "production_labor_price_audit" not in inspector.get_table_names():
        op.create_table(
            "production_labor_price_audit",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("doc_no", sa.String(length=64), nullable=True, comment="单据编号"),
            sa.Column("apply_date", sa.Date(), nullable=True, comment="申请日期"),
            sa.Column("valid_flag", sa.Integer(), nullable=True, comment="有效标志"),
            sa.Column("department_id", sa.Integer(), nullable=True, comment="部门ID"),
            sa.Column("material_id", sa.Integer(), nullable=True, comment="物料ID(引用scm_material.erp_material_id)"),
            sa.Column("material_code", sa.String(length=64), nullable=True, comment="物料代码"),
            sa.Column("labor_price_code", sa.String(length=64), nullable=True, comment="工价表唯一码(业务主键,用于增量同步去重)"),
            sa.Column("labor_price_amount", sa.Numeric(precision=15, scale=4), nullable=True, comment="工价金额"),
            sa.Column("bom_id", sa.Integer(), nullable=True, comment="BOM ID"),
            sa.Column("bom_code", sa.String(length=64), nullable=True, comment="BOM编码"),
            sa.Column("data_source", sa.String(length=32), nullable=False, server_default="erp", comment="数据来源"),
            sa.Column("erp_updated_at", sa.DateTime(), nullable=True, comment="ERP端更新时间(用于增量同步)"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_production_labor_price_audit_code "
        "ON production_labor_price_audit (labor_price_code) "
        "WHERE labor_price_code IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_production_labor_price_audit_apply_date "
        "ON production_labor_price_audit (apply_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_production_labor_price_audit_material_code "
        "ON production_labor_price_audit (material_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_production_labor_price_audit_department_id "
        "ON production_labor_price_audit (department_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_production_labor_price_audit_department_id")
    op.execute("DROP INDEX IF EXISTS ix_production_labor_price_audit_material_code")
    op.execute("DROP INDEX IF EXISTS ix_production_labor_price_audit_apply_date")
    op.execute("DROP INDEX IF EXISTS uq_production_labor_price_audit_code")
    op.execute("DROP TABLE IF EXISTS production_labor_price_audit")
