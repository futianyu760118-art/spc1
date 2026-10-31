"""add permissions field to share_link

Revision ID: add_permissions_to_share_link
Revises: fix_share_link_timezone
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = 'add_permissions_to_share_link'
down_revision = 'fix_share_link_timezone'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('share_link', sa.Column('permissions', JSONB, nullable=True, comment='分享权限，如 ["read","create","update","delete"]'))


def downgrade() -> None:
    op.drop_column('share_link', 'permissions')
