"""add erp_status to sale_order

Revision ID: 0113
Revises: 0112
Create Date: 2026-08-10

说明：新增 sale_order.erp_status 字段（INTEGER），记录 ERP 侧订单状态(整型)。
与 init_database.py 的 migrate_columns["sale_order"]["erp_status"] 一致，
均使用 ADD COLUMN IF NOT EXISTS 幂等写法，二者不会冲突。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0113"
down_revision: Union[str, Sequence[str], None] = "0112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS erp_status INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE sale_order DROP COLUMN IF EXISTS erp_status")
