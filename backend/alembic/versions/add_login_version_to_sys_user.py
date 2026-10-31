"""add_login_version_to_sys_user

Revision ID: add_login_version
Revises: refactor_long_lead
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_login_version'
down_revision: Union[str, None] = 'refactor_long_lead'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sys_user', sa.Column('login_version', sa.Integer(), nullable=False, server_default='0', comment='登录版本号，用于单点登录控制'))
    op.add_column('sys_user', sa.Column('last_token_jti', sa.String(length=64), nullable=True, comment='上一次登录的token jti，用于立即失效'))


def downgrade() -> None:
    op.drop_column('sys_user', 'last_token_jti')
    op.drop_column('sys_user', 'login_version')