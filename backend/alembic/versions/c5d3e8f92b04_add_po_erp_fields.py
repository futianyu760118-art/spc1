"""add po erp fields

Revision ID: c5d3e8f92b04
Revises: 2e8a7cbd0aad
Create Date: 2026-04-14 12:46:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c5d3e8f92b04'
down_revision: Union[str, None] = '2e8a7cbd0aad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_order', sa.Column('material_type_name', sa.String(64), nullable=True))
    op.add_column('purchase_order', sa.Column('material_name', sa.String(256), nullable=True))
    op.add_column('purchase_order', sa.Column('po_price', sa.Numeric(15, 4), nullable=True))
    op.add_column('purchase_order', sa.Column('po_date', sa.Date(), nullable=True))
    op.add_column('purchase_order', sa.Column('data_source', sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column('purchase_order', 'data_source')
    op.drop_column('purchase_order', 'po_date')
    op.drop_column('purchase_order', 'po_price')
    op.drop_column('purchase_order', 'material_name')
    op.drop_column('purchase_order', 'material_type_name')
