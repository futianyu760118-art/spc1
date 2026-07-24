"""add order_inventory_check table

Revision ID: 0100
Revises: 5353
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0100'
down_revision = 'chg_inventory_uq'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scm_order_inventory_check',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_no', sa.String(length=64), nullable=False),
        sa.Column('checked_by', sa.String(length=100), nullable=True),
        sa.Column('checked_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('total_materials', sa.Integer(), nullable=True),
        sa.Column('received_materials', sa.Integer(), nullable=True),
        sa.Column('partial_received_materials', sa.Integer(), nullable=True),
        sa.Column('not_ordered_materials', sa.Integer(), nullable=True),
        sa.Column('overdue_materials', sa.Integer(), nullable=True),
        sa.Column('kit_rate', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('materials_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scm_order_inventory_check_order_no', 'scm_order_inventory_check', ['order_no'])


def downgrade():
    op.drop_index('ix_scm_order_inventory_check_order_no', table_name='scm_order_inventory_check')
    op.drop_table('scm_order_inventory_check')
