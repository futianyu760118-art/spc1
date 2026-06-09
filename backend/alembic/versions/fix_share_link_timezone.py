"""fix share_link timezone columns

Revision ID: fix_share_link_timezone
Revises: add_share_link_table
Create Date: 2026-06-03 11:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'fix_share_link_timezone'
down_revision: Union[str, Sequence[str], None] = 'add_share_link_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('share_link', 'expires_at',
                    type_=sa.DateTime(timezone=True),
                    existing_type=sa.DateTime(timezone=False),
                    nullable=True)
    op.alter_column('share_link', 'created_at',
                    type_=sa.DateTime(timezone=True),
                    existing_type=sa.DateTime(timezone=False),
                    nullable=False)


def downgrade() -> None:
    op.alter_column('share_link', 'expires_at',
                    type_=sa.DateTime(timezone=False),
                    existing_type=sa.DateTime(timezone=True),
                    nullable=True)
    op.alter_column('share_link', 'created_at',
                    type_=sa.DateTime(timezone=False),
                    existing_type=sa.DateTime(timezone=True),
                    nullable=False)
