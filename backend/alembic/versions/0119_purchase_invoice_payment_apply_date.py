"""add payment_apply_date to purchase_invoice

Revision ID: 0119
Revises: 0118
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0119'
down_revision: Union[str, Sequence[str], None] = '0118'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_invoice', sa.Column('payment_apply_date', sa.Date(), nullable=True, comment='付款申请日期'))


def downgrade() -> None:
    op.drop_column('purchase_invoice', 'payment_apply_date')
