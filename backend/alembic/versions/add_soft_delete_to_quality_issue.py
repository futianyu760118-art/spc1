"""add soft-delete (is_deleted) + data_source to quality_issue

Revision ID: add_qi_soft_delete
Revises: add_biz_doc_soft_delete
Create Date: 2026-07-30

说明：
- 为品质异常 quality_issue 增加 is_deleted(软删除标记) 与 data_source(数据来源) 字段，
  支撑"方案C 品质异常删除检测": 增量 upsert 后用全量 erp_quality_id 做差集，把 ERP 端
  已删除的本地记录置 is_deleted=TRUE（软删），仅 data_source='erp' 的记录参与比对，
  manual/excel 来源的手填记录不受影响；ERP 端恢复的记录在下次 upsert 时自动复活。
- is_deleted: BOOLEAN(default FALSE); data_source: VARCHAR(32)(default 'manual')。
- 与 init_database.py 的 migrate_columns["quality_issue"] 完全一致 (项目以
  init_database.py 为运行时真相源；Alembic 仅手动执行，两者并存不会冲突)。
- 使用 ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS 幂等写法。
- revision id 控制在 32 字符以内，规避 alembic_version.version_num 默认 varchar(32) 限制。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_qi_soft_delete"
down_revision: Union[str, Sequence[str], None] = "add_biz_doc_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 数据来源: 区分 erp / manual / excel (删除比对守卫)
    op.execute(
        "ALTER TABLE quality_issue "
        "ADD COLUMN IF NOT EXISTS data_source VARCHAR(32) NOT NULL DEFAULT 'manual'"
    )
    op.execute(
        "COMMENT ON COLUMN quality_issue.data_source IS '数据来源: erp / manual / excel'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quality_issue_data_source "
        "ON quality_issue (data_source)"
    )

    # 2. 软删除标记 (源端已删除)
    op.execute(
        "ALTER TABLE quality_issue "
        "ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "COMMENT ON COLUMN quality_issue.is_deleted IS '是否删除(源端已删除)'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quality_issue_is_deleted "
        "ON quality_issue (is_deleted)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_quality_issue_is_deleted")
    op.execute("DROP INDEX IF EXISTS ix_quality_issue_data_source")
    op.execute("ALTER TABLE quality_issue DROP COLUMN IF EXISTS is_deleted")
    op.execute("ALTER TABLE quality_issue DROP COLUMN IF EXISTS data_source")
