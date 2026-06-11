"""allow nullable position code

Revision ID: allow_nullable_position_code
Revises: add_position_role_mapping
Create Date: 2026-06-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "allow_nullable_position_code"
down_revision: Union[str, Sequence[str], None] = "add_position_role_mapping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "scm_position",
        "position_code",
        existing_type=sa.String(length=64),
        nullable=True,
        existing_comment="岗位编码",
    )


def downgrade() -> None:
    op.alter_column(
        "scm_position",
        "position_code",
        existing_type=sa.String(length=64),
        nullable=False,
        existing_comment="岗位编码",
    )
