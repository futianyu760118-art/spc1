"""add is_closed to purchase_order

Revision ID: add_is_closed_to_purchase_order
Revises: 7314cacebdb6
Create Date: 2026-06-17 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_is_closed_to_purchase_order'
down_revision: Union[str, None] = '7314cacebdb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_order', sa.Column('is_closed', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('purchase_order', 'is_closed')
