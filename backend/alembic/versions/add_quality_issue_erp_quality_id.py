"""add quality issue erp quality id

Revision ID: add_qi_erp_quality_id
Revises: add_last_login_time
Create Date: 2026-05-18 16:05:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_qi_erp_quality_id'
down_revision: Union[str, None] = 'add_last_login_time'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('quality_issue', sa.Column('erp_quality_id', sa.String(length=64), nullable=True))
    op.create_index('uq_quality_issue_erp_quality_id', 'quality_issue', ['erp_quality_id'], unique=True, postgresql_where=sa.text('erp_quality_id IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('uq_quality_issue_erp_quality_id', table_name='quality_issue')
    op.drop_column('quality_issue', 'erp_quality_id')
