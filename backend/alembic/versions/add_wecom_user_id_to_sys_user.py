"""add wecom_user_id to sys_user

为企业微信账号绑定功能新增 sys_user.wecom_user_id 列与部分唯一索引。

Revision ID: add_wecom_user_id_to_sys_user
Revises: add_is_default_password
Create Date: 2026-08-11

说明：
- 该列同时已在 init_database.py 的 migrate_columns 中注册（运行时真正的迁移源），
  本 Alembic 修订仅用于保持 ad-hoc Alembic 历史一致。
- Alembic 图当前存在多个 head，此处按 sys_user 相关 head 链接；
  若要线性 upgrade 到本修订，可用 `alembic upgrade add_wecom_user_id_to_sys_user`。
"""

from typing import Sequence, Union

from alembic import op


revision: str = "add_wecom_user_id_to_sys_user"
down_revision: Union[str, Sequence[str], None] = "add_is_default_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 列：每个系统用户可绑定一个企业微信 userid（可空）
    op.execute("ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS wecom_user_id VARCHAR(64)")
    # 部分唯一索引：每个企业微信 userid 至多绑定一个系统用户；
    # WHERE ... IS NOT NULL 使未绑定的用户（NULL）互不冲突。
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_sys_user_wecom_user_id "
        "ON sys_user (wecom_user_id) WHERE wecom_user_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_sys_user_wecom_user_id")
    op.execute("ALTER TABLE sys_user DROP COLUMN IF EXISTS wecom_user_id")
