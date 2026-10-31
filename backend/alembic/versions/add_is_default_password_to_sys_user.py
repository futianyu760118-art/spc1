"""add is_default_password to sys_user

Revision ID: add_is_default_password
Revises: allow_nullable_position_code
Create Date: 2026-06-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_is_default_password"
down_revision: Union[str, Sequence[str], None] = "allow_nullable_position_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('sys_user', sa.Column('is_default_password', sa.Boolean(), nullable=False, server_default=sa.true(), comment='是否默认密码，首次登录强制修改'))


def downgrade():
    op.drop_column('sys_user', 'is_default_password')