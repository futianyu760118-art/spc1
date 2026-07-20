"""add supplier_id/order_unit_price/last_outbound_date to scm_material

Revision ID: add_scm_material_3cols
Revises: add_pto_sale_order_id, add_owner_id_to_purchase_order,
         add_md_display_fields, 0102, add_po_owner_id,
         add_ix_scm_bom_detail_material_id, fix_scm_id_columns_to_integer,
         add_supplier_account_to_purchase_order
Create Date: 2026-07-16

说明：
- 为 scm_material 增加三个字段：supplier_id(供应商ID)、
  order_unit_price(订货单价)、last_outbound_date(最后出库日期)。
- 该迁移同时合并当前 8 个 head，使迁移图收敛为单一 head。
- revision id 控制在 32 字符以内，规避 alembic_version.version_num
  默认 varchar(32) 的限制（env.py 已加幂等扩列保护）。
- 使用 ADD/DROP COLUMN IF NOT EXISTS/IF EXISTS 的幂等写法，
  与 init_database.py 的 migrate_columns 风格一致，两者并存也不会冲突。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_scm_material_3cols"
down_revision: Union[str, Sequence[str], None] = (
    "add_pto_sale_order_id",
    "add_owner_id_to_purchase_order",
    "add_md_display_fields",
    "0102",
    "add_po_owner_id",
    "add_ix_scm_bom_detail_material_id",
    "fix_scm_id_columns_to_integer",
    "add_supplier_account_to_purchase_order",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scm_material "
        "ADD COLUMN IF NOT EXISTS supplier_id INTEGER"
    )
    op.execute(
        "ALTER TABLE scm_material "
        "ADD COLUMN IF NOT EXISTS order_unit_price NUMERIC(15,4)"
    )
    op.execute(
        "ALTER TABLE scm_material "
        "ADD COLUMN IF NOT EXISTS last_outbound_date DATE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scm_material DROP COLUMN IF EXISTS last_outbound_date")
    op.execute("ALTER TABLE scm_material DROP COLUMN IF EXISTS order_unit_price")
    op.execute("ALTER TABLE scm_material DROP COLUMN IF EXISTS supplier_id")
