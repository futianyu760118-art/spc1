"""add covered_products JSONB to scm_inventory_check

Revision ID: add_inv_check_covered
Revises: add_scm_material_property
Create Date: 2026-07-21

说明：
- 为 scm_inventory_check 增加 covered_products(JSONB) 字段，记录每次订单盘点
  覆盖的产品行 [{product_code, bom_no, line_no, product_name, order_qty}]，
  用于支持"按订单查看哪些产品已盘点"的可追溯性。
- 使用 ADD/DROP COLUMN IF NOT EXISTS/IF EXISTS 的幂等写法，与 init_database.py
  的 migrate_columns 风格一致，两者并存也不会冲突。
  (项目以 init_database.py 为运行时真相源；Alembic 仅手动执行。)
- revision id 控制在 32 字符以内，规避 alembic_version.version_num
  默认 varchar(32) 的限制。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_inv_check_covered"
down_revision: Union[str, Sequence[str], None] = "add_scm_material_property"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scm_inventory_check "
        "ADD COLUMN IF NOT EXISTS covered_products JSONB"
    )
    # 带列注释，便于 DBA 在 psql \d+ 中辨识(与 ORM model comment 一致)
    op.execute(
        "COMMENT ON COLUMN scm_inventory_check.covered_products IS "
        "'本次盘点覆盖的产品行 [{product_code,bom_no,line_no,product_name,order_qty}]'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scm_inventory_check DROP COLUMN IF EXISTS covered_products")
