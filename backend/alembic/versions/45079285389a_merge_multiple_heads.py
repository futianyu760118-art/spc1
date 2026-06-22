"""merge multiple heads

Revision ID: 45079285389a
Revises: 3bebed571ad2
Create Date: 2026-06-22 12:15:10.010938
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '45079285389a'
down_revision: Union[str, None] = '3bebed571ad2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
