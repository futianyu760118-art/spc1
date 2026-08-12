"""add reason column to share_link

Revision ID: 0112
Revises: 0111
Create Date: 2026-08-05

说明：新增 share_link.reason 字段，记录分享原因（分享卡片展示）。
对应 spec §WecomShare 分享原因。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0112"
down_revision: Union[str, Sequence[str], None] = "0111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE share_link ADD COLUMN IF NOT EXISTS reason VARCHAR(256)")


def downgrade() -> None:
    op.execute("ALTER TABLE share_link DROP COLUMN IF EXISTS reason")
