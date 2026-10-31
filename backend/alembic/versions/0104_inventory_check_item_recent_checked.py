"""add recent_checked_check_no / recent_checked_date to scm_inventory_check_item

Revision ID: 0104
Revises: 0103
Create Date: 2026-07-29

说明：订单盘点按 (物料×仓库) 去重 + 跳过近期已盘。新增两列用于记录
「该行在建单时由哪份近期盘点单预填补」；NULL = 普通行（需手工盘点）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0104"
down_revision: Union[str, Sequence[str], None] = "0103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scm_inventory_check_item",
        sa.Column("recent_checked_check_no", sa.String(length=32), nullable=True,
                  comment="近期已盘来源盘点单号(快照);NULL=普通行"),
    )
    op.add_column(
        "scm_inventory_check_item",
        sa.Column("recent_checked_date", sa.Date(), nullable=True,
                  comment="近期已盘来源盘点日期(快照)"),
    )


def downgrade() -> None:
    op.drop_column("scm_inventory_check_item", "recent_checked_date")
    op.drop_column("scm_inventory_check_item", "recent_checked_check_no")
