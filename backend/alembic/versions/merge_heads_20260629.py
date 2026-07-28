"""merge heads

Revision ID: merge_heads_20260629
Revises: add_error_message_to_call_log, add_ui_preferences_to_sys_user
Create Date: 2026-06-29

"""
from alembic import op

revision = 'merge_heads_20260629'
down_revision = ('add_error_message_to_call_log', 'add_ui_preferences_sys_user')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
