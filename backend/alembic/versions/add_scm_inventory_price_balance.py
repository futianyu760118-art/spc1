"""add unit_price/ending_balance to scm_inventory

Revision ID: add_scm_inventory_price_balance
Revises: add_front_process_record
Create Date: 2026-07-20

说明：
- 为 scm_inventory 增加两个字段：unit_price(库存单价, NUMERIC(15,6))、
  ending_balance(期末余额, NUMERIC(15,2))。
- 使用 ADD/DROP COLUMN IF NOT EXISTS/IF EXISTS 的幂等写法，
  与 init_database.py 的 migrate_columns 风格一致，两者并存也不会冲突。
  (项目以 init_database.py 为运行时真相源；Alembic 仅手动执行。)
- 既有列已 NOT NULL，故 ALTER 时带 DEFAULT 0，避免 PostgreSQL 对存量行报错。
- revision id 控制在 32 字符以内，规避 alembic_version.version_num
  默认 varchar(32) 的限制。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_scm_inventory_price_balance"
down_revision: Union[str, Sequence[str], None] = "add_front_process_record"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scm_inventory "
        "ADD COLUMN IF NOT EXISTS unit_price NUMERIC(15,6) NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE scm_inventory "
        "ADD COLUMN IF NOT EXISTS ending_balance NUMERIC(15,2) NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scm_inventory DROP COLUMN IF EXISTS ending_balance")
    op.execute("ALTER TABLE scm_inventory DROP COLUMN IF EXISTS unit_price")
