"""add soft-delete (is_deleted) to business_document

Revision ID: add_biz_doc_soft_delete
Revises: 0104
Create Date: 2026-07-29

说明：
- 为共享台账 business_document（产品封样 product_sample / 作业指导书 work_instruction
  / 订单标准 order_standard）增加 is_deleted 字段，引入与"归档"解耦的软删除。
- 将 (doc_type, code) 唯一索引改为部分唯一索引（仅 is_deleted = 0 生效），
  使软删除后同编码可被新建复用。
- 使用 ADD/DROP COLUMN IF [NOT] EXISTS、DROP/CREATE INDEX IF [NOT] EXISTS 的幂等写法，
  与 init_database.py 的 migrate_columns / migrate_business_document_soft_delete_index
  风格一致，两者并存也不会冲突。
  (项目以 init_database.py 为运行时真相源；Alembic 仅手动执行。)
- revision id 控制在 32 字符以内，规避 alembic_version.version_num
  默认 varchar(32) 的限制。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_biz_doc_soft_delete"
down_revision: Union[str, Sequence[str], None] = "0104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增软删除字段（沿用 basicdata 域 is_deleted Integer default 0 约定）
    op.execute(
        "ALTER TABLE business_document "
        "ADD COLUMN IF NOT EXISTS is_deleted INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "COMMENT ON COLUMN business_document.is_deleted IS '是否删除 0否1是'"
    )
    # 普通索引（与 ORM model 的 index=True 对齐，加速列表过滤）
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_business_document_is_deleted "
        "ON business_document (is_deleted)"
    )

    # 2. (doc_type, code) 唯一索引改为部分唯一：仅未删除行参与唯一约束
    op.execute("DROP INDEX IF EXISTS uq_business_document_type_code")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_business_document_type_code "
        "ON business_document (doc_type, code) WHERE is_deleted = 0"
    )


def downgrade() -> None:
    # 回滚：还原为全表唯一索引，并移除 is_deleted 列
    op.execute("DROP INDEX IF EXISTS uq_business_document_type_code")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_business_document_type_code "
        "ON business_document (doc_type, code)"
    )
    op.execute("DROP INDEX IF EXISTS ix_business_document_is_deleted")
    op.execute("ALTER TABLE business_document DROP COLUMN IF EXISTS is_deleted")
