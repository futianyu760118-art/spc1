"""add material_type to mrp_plan_order

Revision ID: add_mrp_plan_order_material_type
Revises: add_mrp_plan_mat_property
Create Date: 2026-06-23 17:00:00.000000

说明：
    为 MRP 计划订单新增 物料类型 字段，
    用于齐套分析展开行直接展示计划订单的物料类型。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_mrp_plan_order_material_type'
down_revision: Union[str, None] = 'add_mrp_plan_mat_property'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'mrp_plan_order',
        sa.Column(
            'material_type',
            sa.String(length=64),
            nullable=True,
            comment='物料类型',
        ),
    )


def downgrade() -> None:
    op.drop_column('mrp_plan_order', 'material_type')
