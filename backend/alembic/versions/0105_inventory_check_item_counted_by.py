"""add counted_by_user_id / counted_by / counted_at and ix_sci_counted_by_date to scm_inventory_check_item

Revision ID: 0105
Revises: 0104
Create Date: 2026-08-03

说明：物料盘点个人台账。在盘点明细表增加「最后录入实盘数量」的稳定归属字段
与复合索引；保留现有 checked_by / checked_at 作为「标记已盘」语义。历史回填
按 checked_by = sys_user.username 匹配，排除 system-recent 沿用行与近期已盘行。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0105"
down_revision: Union[str, Sequence[str], None] = "0104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scm_inventory_check_item",
        sa.Column("counted_by_user_id", sa.BigInteger(), nullable=True,
                  comment="最后录入实盘数量的用户ID"),
    )
    op.add_column(
        "scm_inventory_check_item",
        sa.Column("counted_by", sa.String(length=100), nullable=True,
                  comment="最后录入实盘数量的用户名称快照"),
    )
    op.add_column(
        "scm_inventory_check_item",
        sa.Column("counted_at", sa.DateTime(), nullable=True,
                  comment="最后录入实盘数量的时间"),
    )
    op.create_index(
        "ix_sci_counted_by_date",
        "scm_inventory_check_item",
        ["counted_by_user_id", "counted_at"],
        unique=False,
    )
    op.execute(
        """
        UPDATE scm_inventory_check_item AS i
        SET counted_by_user_id = u.id,
            counted_by = i.checked_by,
            counted_at = i.checked_at
        FROM sys_user AS u
        WHERE i.counted_by_user_id IS NULL
          AND i.checked_by IS NOT NULL
          AND i.checked_by <> 'system-recent'
          AND i.recent_checked_check_no IS NULL
          AND i.checked_by = u.username
        """
    )


def downgrade() -> None:
    op.drop_index("ix_sci_counted_by_date", table_name="scm_inventory_check_item")
    op.drop_column("scm_inventory_check_item", "counted_at")
    op.drop_column("scm_inventory_check_item", "counted_by")
    op.drop_column("scm_inventory_check_item", "counted_by_user_id")