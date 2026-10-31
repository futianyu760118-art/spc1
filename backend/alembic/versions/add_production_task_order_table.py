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
