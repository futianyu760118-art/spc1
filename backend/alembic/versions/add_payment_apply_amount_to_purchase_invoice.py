"""add payment_apply_amount to purchase_invoice
Revision ID: add_pi_payment_apply_amt

Revises: merge_heads_20260629
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_pi_payment_apply_amt'
down_revision = 'merge_heads_20260629'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('purchase_invoice', sa.Column('payment_apply_amount', sa.Numeric(precision=15, scale=2), nullable=True, comment='付款申请金额'))


def downgrade() -> None:
    op.drop_column('purchase_invoice', 'payment_apply_amount')
