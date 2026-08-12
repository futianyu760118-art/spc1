"""add version column to scm_inventory_check and scm_inventory_check_item

Revision ID: 0115
Revises: 0114
Create Date: 2026-08-11

说明：为乐观锁新增 scm_inventory_check.version / scm_inventory_check_item.version
（INTEGER NOT NULL DEFAULT 0）。每次行/头更新时由 service 层 +1。
与 init_database.py 的 migrate_columns 同语句（ADD COLUMN IF NOT EXISTS），
二者并存不冲突；容器启动以 init_database.py 为真相源，本 Alembic 仅手动运行时兜底。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0115"
down_revision: Union[str, Sequence[str], None] = "0114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE scm_inventory_check ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE scm_inventory_check_item ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE scm_inventory_check_item DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE scm_inventory_check DROP COLUMN IF EXISTS version")
