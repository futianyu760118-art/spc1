"""add production_task_order.sale_order_id

Revision ID: add_pto_sale_order_id
Revises: add_production_task_order
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_pto_sale_order_id"
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
