"""add oa_detail_id to production_daily_report + unique index (oa_id, oa_detail_id)

Revision ID: add_pdr_oa_detail_id
Revises: add_chk_level_and_cocheck
Create Date: 2026-07-27

说明：
- 为 production_daily_report 增加 oa_detail_id INTEGER（明细ID）。
- 将唯一索引由 (oa_id) 改为 (oa_id, oa_detail_id)：
  先 DROP 旧索引 uq_production_daily_report_oa_id，
  再 CREATE UNIQUE INDEX uq_production_daily_report_oa_id_detail
  ON production_daily_report (oa_id, oa_detail_id)
  WHERE oa_id IS NOT NULL AND oa_detail_id IS NOT NULL。
  oa_detail_id 为 NULL 的行不参与唯一性约束。
- 使用 ADD/DROP COLUMN IF NOT EXISTS/IF EXISTS 与 DROP/CREATE INDEX IF EXISTS/IF NOT EXISTS
  的幂等写法，与 init_database.py 的 migrate_columns / migrate_production_daily_report_index
  风格一致，两者并存也不会冲突。
  (项目以 init_database.py 为运行时真相源；Alembic 仅手动执行。)
- revision id 控制在 32 字符以内，规避 alembic_version.version_num
  默认 varchar(32) 的限制。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_pdr_oa_detail_id"
down_revision: Union[str, Sequence[str], None] = "add_chk_level_and_cocheck"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE production_daily_report "
        "ADD COLUMN IF NOT EXISTS oa_detail_id INTEGER"
    )
    op.execute(
        "ALTER TABLE production_daily_report "
        "ALTER COLUMN oa_detail_id TYPE INTEGER "
        "USING (oa_detail_id::integer)"
    )
    op.execute(
        "COMMENT ON COLUMN production_daily_report.oa_detail_id IS '明细ID'"
    )
    op.execute("DROP INDEX IF EXISTS uq_production_daily_report_oa_id")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_production_daily_report_oa_id_detail "
        "ON production_daily_report (oa_id, oa_detail_id) "
        "WHERE oa_id IS NOT NULL AND oa_detail_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_production_daily_report_oa_id_detail")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_production_daily_report_oa_id "
        "ON production_daily_report (oa_id) WHERE oa_id IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE production_daily_report DROP COLUMN IF EXISTS oa_detail_id"
    )
