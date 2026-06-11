"""add position management

Revision ID: add_position_management
Revises: add_topbar_permissions
Create Date: 2026-06-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_position_management"
down_revision: Union[str, Sequence[str], None] = "add_topbar_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scm_position",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("position_code", sa.String(length=64), nullable=True, comment="岗位编码"),
        sa.Column("position_name", sa.String(length=100), nullable=False, comment="岗位名称"),
        sa.Column("status", sa.Integer(), nullable=False, server_default="1", comment="状态"),
        sa.Column("data_source", sa.String(length=32), nullable=True),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("position_code", name="uq_scm_position_code"),
    )
    op.create_index("idx_scm_position_name", "scm_position", ["position_name"])
    op.add_column("scm_employee", sa.Column("position_id", sa.BigInteger(), nullable=True, comment="岗位ID"))
    op.create_index("idx_scm_employee_position_id", "scm_employee", ["position_id"])

    op.execute(
        """
        INSERT INTO sync_sql_config (
            sync_type,
            description,
            sql_text,
            field_mapping_json,
            sync_interval,
            sync_strategy,
            sync_priority,
            sync_enabled,
            is_active,
            created_by
        )
        VALUES (
            'positions',
            '岗位 - 从OA岗位表拉取',
            'SELECT position_code, position_name, status FROM T_BD_POSITION ORDER BY position_code',
            NULL,
            '1d',
            'full',
            18,
            false,
            false,
            'admin'
        )
        ON CONFLICT (sync_type) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM sync_sql_config WHERE sync_type = 'positions'")
    op.drop_index("idx_scm_employee_position_id", table_name="scm_employee")
    op.drop_column("scm_employee", "position_id")
    op.drop_index("idx_scm_position_name", table_name="scm_position")
    op.drop_table("scm_position")
