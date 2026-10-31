"""merge multiple heads

Revision ID: 3bebed571ad2
Revises: add_production_scheduling_fields, allow_nullable_position_code
Create Date: 2026-06-22 12:14:24.738923
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '3bebed571ad2'
down_revision: Union[str, None] = ('add_production_scheduling_fields', 'allow_nullable_position_code')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
