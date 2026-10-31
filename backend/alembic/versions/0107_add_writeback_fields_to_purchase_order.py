"""add last_writeback_at / last_writeback_status to purchase_order

Revision ID: 0107
Revises: 0106
Create Date: 2026-08-03

说明：采购订单表加 2 个轻量字段,用于列表页显示"是否已回写 ERP"。
- last_writeback_at: 最近一次成功回写时间
- last_writeback_status: success / failed
两列可空,与现有 data_source 标识无关,纯展示用,不参与回写逻辑。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0107"
down_revision: Union[str, Sequence[str], None] = "0106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "purchase_order",
        sa.Column("last_writeback_at", sa.DateTime(), nullable=True,
                  comment="最近一次成功回写时间"),
    )
    op.add_column(
        "purchase_order",
        sa.Column("last_writeback_status", sa.String(length=16), nullable=True,
                  comment="success/failed,列表页展示用"),
    )


def downgrade() -> None:
    op.drop_column("purchase_order", "last_writeback_status")
    op.drop_column("purchase_order", "last_writeback_at")