"""add oa_id to production_labor_price_audit

Revision ID: add_lpa_oa_id
Revises: add_labor_price_audit
Create Date: 2026-07-28

说明：
- 为 production_labor_price_audit 增加 oa_id VARCHAR(64)（ERP/OA 唯一键）。
- 幂等：ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS，与 create_all / init_database.py 并存不冲突。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_lpa_oa_id"
down_revision: Union[str, None] = "add_labor_price_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE production_labor_price_audit "
        "ADD COLUMN IF NOT EXISTS oa_id VARCHAR(64)"
    )
    op.execute(
        "COMMENT ON COLUMN production_labor_price_audit.oa_id IS 'ERP/OA 唯一键(业务主键)'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_production_labor_price_audit_oa_id "
        "ON production_labor_price_audit (oa_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_production_labor_price_audit_oa_id")
    op.execute(
        "ALTER TABLE production_labor_price_audit DROP COLUMN IF EXISTS oa_id"
    )
