"""add timestamps to scm_material

Revision ID: add_timestamps_to_scm_material
Revises: 20260629_add_field_synced_at
Create Date: 2026-06-29

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_timestamps_to_scm_material'
down_revision = '20260629_add_field_synced_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('scm_material', sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=True))
    op.add_column('scm_material', sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=True))


def downgrade() -> None:
    op.drop_column('scm_material', 'update_time')
    op.drop_column('scm_material', 'create_time')
