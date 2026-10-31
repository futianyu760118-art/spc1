"""add condition params to sync sql config

Revision ID: add_condition_params
Revises: c5d3e8f92b04
Create Date: 2026-04-14 15:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_condition_params'
down_revision: Union[str, None] = 'c5d3e8f92b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sync_sql_config', sa.Column('condition_params_json', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('sync_sql_config', 'condition_params_json')
