"""add error_message to data_supply_call_log

Revision ID: add_error_message_to_call_log
Revises: add_timestamps_to_scm_material
Create Date: 2026-06-29

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_error_message_to_call_log'
down_revision = 'add_timestamps_to_scm_material'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('data_supply_call_log', sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'))


def downgrade() -> None:
    op.drop_column('data_supply_call_log', 'error_message')
