"""unique index on oa_id for production_labor_price_audit

Revision ID: uq_lpa_oa_id
Revises: add_lpa_oa_id
Create Date: 2026-07-28

说明：
- 将 oa_id 的普通索引替换为 partial unique 索引（NULL 不参与唯一约束），
  与 production_daily_report 的 oa_id 约定一致。
- 幂等：DROP/CREATE IF EXISTS。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "uq_lpa_oa_id"
down_revision: Union[str, None] = "add_lpa_oa_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_production_labor_price_audit_oa_id")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_production_labor_price_audit_oa_id "
        "ON production_labor_price_audit (oa_id) "
        "WHERE oa_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_production_labor_price_audit_oa_id")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_production_labor_price_audit_oa_id "
        "ON production_labor_price_audit (oa_id)"
    )
