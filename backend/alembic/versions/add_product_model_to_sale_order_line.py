"""add product_model to sale_order_line

Revision ID: add_product_model
Revises: fix_order_no_idx
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_product_model'
down_revision = 'fix_order_no_idx'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sale_order_line', sa.Column('product_model', sa.String(128), nullable=True, comment='产品型号'))


def downgrade() -> None:
    op.drop_column('sale_order_line', 'product_model')
