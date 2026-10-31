"""merge_heads

Revision ID: 402b24e98d7e
Revises: add_is_closed_to_sale_order, add_org_position_to_sys_role
Create Date: 2026-06-17 09:18:10.890100
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '402b24e98d7e'
down_revision: Union[str, None] = ('add_is_closed_to_sale_order', 'add_org_position_to_sys_role')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
