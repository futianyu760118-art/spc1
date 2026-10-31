"""add oa position id to position

Revision ID: add_oa_position_id_to_position
Revises: add_position_management
Create Date: 2026-06-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_oa_position_id_to_position"
down_revision: Union[str, Sequence[str], None] = "add_position_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE scm_position ADD COLUMN IF NOT EXISTS oa_position_id VARCHAR(64)")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_scm_position_oa_position_id
        ON scm_position (oa_position_id)
        WHERE oa_position_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE sync_sql_config
        SET sql_text = 'SELECT position_code, oa_position_id, position_name, status FROM T_BD_POSITION ORDER BY position_code'
        WHERE sync_type = 'positions'
          AND sql_text = 'SELECT position_code, position_name, status FROM T_BD_POSITION ORDER BY position_code'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_scm_position_oa_position_id")
    op.execute("ALTER TABLE scm_position DROP COLUMN IF EXISTS oa_position_id")
    op.execute(
        """
        UPDATE sync_sql_config
        SET sql_text = 'SELECT position_code, position_name, status FROM T_BD_POSITION ORDER BY position_code'
        WHERE sync_type = 'positions'
          AND sql_text = 'SELECT position_code, oa_position_id, position_name, status FROM T_BD_POSITION ORDER BY position_code'
        """
    )
