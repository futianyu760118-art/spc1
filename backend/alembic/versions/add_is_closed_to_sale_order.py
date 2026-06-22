"""add is_closed to sale_order

Revision ID: add_is_closed_to_sale_order
Revises: fix_sale_order_unique_index
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_is_closed_to_sale_order'
down_revision = 'add_supplier_name_to_sys_user'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sale_order', sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.text('false'), comment='是否关闭'))


def downgrade() -> None:
    op.drop_column('sale_order', 'is_closed')
