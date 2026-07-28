"""add field_synced_at to sale_order

Revision ID: 20260629_add_field_synced_at
Revises: add_is_closed_to_sale_order
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa


revision = '20260629_add_field_synced_at'
down_revision = 'add_is_closed_to_sale_order'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS field_synced_at JSONB")
    op.execute("COMMENT ON COLUMN sale_order.field_synced_at IS '字段级同步时间 {field_name: ISO8601 str}'")


def downgrade():
    op.execute("ALTER TABLE sale_order DROP COLUMN IF EXISTS field_synced_at")
