"""add_last_login_time_to_sys_user

Revision ID: add_last_login_time
Revises: add_login_version
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_last_login_time'
down_revision: Union[str, None] = 'add_login_version'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sys_user', sa.Column('last_login_time', sa.DateTime(), nullable=True, comment='最后一次登录时间'))


def downgrade() -> None:
    op.drop_column('sys_user', 'last_login_time')