"""merge heads before sys_permission

Revision ID: merge_heads_before_perm
Revises: 80ec41a78266, sale_order_is_closed_to_int
Create Date: 2026-06-23 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "merge_heads_before_perm"
down_revision: Union[str, Sequence[str], None] = ("80ec41a78266", "sale_order_is_closed_to_int")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
