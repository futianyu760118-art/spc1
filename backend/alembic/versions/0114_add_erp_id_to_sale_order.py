"""add erp_id to sale_order

Revision ID: 0114
Revises: 0113
Create Date: 2026-08-10

说明：新增 sale_order.erp_id 字段（INTEGER），存储 ERP 订单主键ID，
用于与 ERP 系统的订单唯一标识对齐，配合 erp_status 做状态映射。
与 init_database.py 的 migrate_columns["sale_order"]["erp_id"] 一致，
均使用 ADD COLUMN IF NOT EXISTS 幂等写法，二者不会冲突。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0114"
down_revision: Union[str, Sequence[str], None] = "0113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS erp_id INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE sale_order DROP COLUMN IF EXISTS erp_id")
