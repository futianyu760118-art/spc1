"""add wh_id/wh_name/wh_code to scm_inventory_check_item for split-by-warehouse

Revision ID: 0103
Revises: 0102
Create Date: 2026-07-28

说明：物料盘点明细按仓库拆行。scm_inventory_check_item 增加仓库三列（建单时快照），
NULL 兼容历史老盘点单和物料无库存时的合成行。所有列可空，不强制重写存量数据。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0103"
down_revision: Union[str, Sequence[str], None] = "0102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scm_inventory_check_item",
        sa.Column("wh_id", sa.Integer(), nullable=True,
                  comment="仓库ID(快照);NULL=历史老盘点单或(未入库)"),
    )
    op.add_column(
        "scm_inventory_check_item",
        sa.Column("wh_name", sa.String(length=50), nullable=True,
                  comment="仓库名称(建单时快照)"),
    )
    op.add_column(
        "scm_inventory_check_item",
        sa.Column("wh_code", sa.String(length=20), nullable=True,
                  comment="仓库编码(建单时快照)"),
    )
    op.create_index(
        "ix_sci_wh",
        "scm_inventory_check_item",
        ["check_id", "material_id", "wh_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sci_wh", table_name="scm_inventory_check_item")
    op.drop_column("scm_inventory_check_item", "wh_code")
    op.drop_column("scm_inventory_check_item", "wh_name")
    op.drop_column("scm_inventory_check_item", "wh_id")