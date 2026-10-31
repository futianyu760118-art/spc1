"""add share_link table

Revision ID: add_share_link_table
Revises: add_order_nature, a1b2c3d4e5f6
Create Date: 2026-06-03 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_share_link_table'
down_revision: Union[str, Sequence[str], None] = ('add_order_nature', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'share_link',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('token', sa.String(64), nullable=False, comment='分享唯一标识'),
        sa.Column('target_path', sa.String(512), nullable=False, comment='目标页面路径'),
        sa.Column('target_params', postgresql.JSONB(), nullable=True, comment='额外参数'),
        sa.Column('created_by', sa.Integer(), nullable=False, comment='创建人 user_id'),
        sa.Column('expires_at', sa.DateTime(), nullable=True, comment='过期时间，null 表示永久'),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default='false', comment='是否已撤销'),
        sa.Column('access_count', sa.Integer(), nullable=False, server_default='0', comment='访问次数'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_share_link_token', 'share_link', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_share_link_token', table_name='share_link')
    op.drop_table('share_link')
