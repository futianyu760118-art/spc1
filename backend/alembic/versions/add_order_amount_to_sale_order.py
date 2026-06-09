"""add order_amount to sale_order and sale_order_line

Revision ID: add_order_amount
Revises: add_qi_erp_quality_id
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_order_amount'
down_revision = 'add_qi_erp_quality_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sale_order', sa.Column('order_amount', sa.Numeric(15, 2), nullable=True, comment='金额'))
    op.add_column('sale_order_line', sa.Column('order_amount', sa.Numeric(15, 2), nullable=True, comment='金额'))


def downgrade() -> None:
    op.drop_column('sale_order_line', 'order_amount')
    op.drop_column('sale_order', 'order_amount')
