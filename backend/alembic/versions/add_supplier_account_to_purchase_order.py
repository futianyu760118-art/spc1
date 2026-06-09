"""add supplier account to purchase_order

Revision ID: add_supplier_account_to_purchase_order
Revises: c5d3e8f92b04
Create Date: 2026-05-29 18:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_supplier_account_to_purchase_order'
down_revision: Union[str, None] = 'c5d3e8f92b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_order', sa.Column('supplier_account', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('purchase_order', 'supplier_account')

