"""add ui_preferences to sys_user

Revision ID: add_ui_preferences_sys_user
Revises: add_mrp_plan_stock_audit_date
Create Date: 2026-06-25

说明：
    为 sys_user 新增 ui_preferences（JSONB）字段，用于存储各页面的 UI 偏好（如列可见性）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'add_ui_preferences_sys_user'
down_revision: Union[str, None] = 'add_mrp_plan_stock_audit_date'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sys_user',
        sa.Column(
            'ui_preferences',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='UI偏好设置（如各页面列可见性等）',
        ),
    )


def downgrade() -> None:
    op.drop_column('sys_user', 'ui_preferences')
