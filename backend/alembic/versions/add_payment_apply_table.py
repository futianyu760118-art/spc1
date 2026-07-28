"""add payment_apply table

Revision ID: add_payment_apply_table
Revises: add_pi_payment_apply_amt
Create Date: 2026-07-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_payment_apply_table'
down_revision: Union[str, None] = 'add_pi_payment_apply_amt'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_apply',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('payment_apply_no', sa.String(length=64), nullable=False, comment='付款申请编号'),
        sa.Column('doc_no', sa.String(length=64), nullable=True, comment='单据编号'),
        sa.Column('doc_date', sa.Date(), nullable=True, comment='单据日期'),
        sa.Column('subsystem_id', sa.String(length=64), nullable=True, comment='子系统ID（ERP来源子系统标识）'),
        sa.Column('paid_amount', sa.Numeric(precision=15, scale=2), nullable=True, comment='已付款金额'),
        sa.Column('data_source', sa.String(length=32), nullable=True, comment='数据来源（erp/manual）'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payment_apply_no', name='uq_payment_apply_no'),
    )
    op.create_index(op.f('ix_payment_apply_payment_apply_no'), 'payment_apply', ['payment_apply_no'], unique=False)
    op.create_index(op.f('ix_payment_apply_doc_no'), 'payment_apply', ['doc_no'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payment_apply_doc_no'), table_name='payment_apply')
    op.drop_index(op.f('ix_payment_apply_payment_apply_no'), table_name='payment_apply')
    op.drop_table('payment_apply')
