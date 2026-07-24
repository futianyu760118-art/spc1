"""add paid_amount to purchase_invoice

Revision ID: add_pi_paid_amt
Revises: add_payment_apply_table
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_pi_paid_amt'
down_revision: Union[str, None] = 'add_payment_apply_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_invoice', sa.Column('paid_amount', sa.Numeric(precision=15, scale=2), nullable=True, comment='已付款金额'))


def downgrade() -> None:
    op.drop_column('purchase_invoice', 'paid_amount')
