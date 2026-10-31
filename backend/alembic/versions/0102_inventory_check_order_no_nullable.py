"""make scm_inventory_check.order_no nullable for manual stock check

Revision ID: 0102
Revises: 0101
Create Date: 2026-07-15

说明：将 scm_inventory_check.order_no 由 NOT NULL 改为可空，
用于支持 manual 类型独立物料盘点(无订单号场景)。
现有数据全部为订单盘点,order_no 非空,无需数据回填。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0102"
down_revision: Union[str, Sequence[str], None] = "0101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "scm_inventory_check",
        "order_no",
        existing_type=sa.String(length=64),
        nullable=True,
        existing_comment="触发起源订单号(manual 类型可空)",
    )


def downgrade() -> None:
    op.alter_column(
        "scm_inventory_check",
        "order_no",
        existing_type=sa.String(length=64),
        nullable=False,
        existing_comment="触发起源订单号(manual 类型可空)",
    )
