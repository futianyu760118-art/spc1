"""add index on scm_bom_detail.material_id

Revision ID: add_ix_scm_bom_detail_material_id
Revises: sale_order_is_closed_to_int
Create Date: 2026-07-15 10:00:00.000000

说明：为 scm_bom_detail.material_id 添加单列索引,
加速物料盘点反查订单(GET /materials/stock-check/material-orders)性能。
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'add_ix_scm_bom_detail_material_id'
down_revision: Union[str, None] = 'sale_order_is_closed_to_int'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_scm_bom_detail_material_id ON scm_bom_detail (material_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scm_bom_detail_material_id")
