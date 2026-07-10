"""add payment_order_id to purchase_invoice

Revision ID: add_pi_payment_order_id
Revises: add_pi_paid_amt
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_pi_payment_order_id'
down_revision: Union[str, None] = 'add_pi_paid_amt'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_invoice', sa.Column('payment_order_id', sa.Integer(), nullable=True, comment='付款单ID'))


def downgrade() -> None:
    op.drop_column('purchase_invoice', 'payment_order_id')
