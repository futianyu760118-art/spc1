"""add stock_qty and audit_date to mrp_plan_order

Revision ID: add_mrp_plan_stock_audit_date
Revises: add_allowed_endpoints_json
Create Date: 2026-06-24

说明：
    为 MRP 计划订单新增 库存数量 和 审核日期 字段。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'add_mrp_plan_stock_audit_date'
down_revision: Union[str, None] = 'add_allowed_endpoints_json'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(bind, table_name: str) -> set:
    insp = inspect(bind)
    if table_name not in insp.get_table_names():
        return set()
    return {c['name'] for c in insp.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind, 'mrp_plan_order')

    if 'stock_qty' not in existing:
        op.add_column(
            'mrp_plan_order',
            sa.Column(
                'stock_qty',
                sa.Numeric(precision=15, scale=2),
                nullable=True,
                comment='库存数量',
            ),
        )
    if 'audit_date' not in existing:
        op.add_column(
            'mrp_plan_order',
            sa.Column(
                'audit_date',
                sa.Date(),
                nullable=True,
                comment='审核日期',
            ),
        )


def downgrade() -> None:
    op.drop_column('mrp_plan_order', 'audit_date')
    op.drop_column('mrp_plan_order', 'stock_qty')
