"""add manager_oa_user_id to employee

Revision ID: add_manager_oa_user_id_to_employee
Revises:
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa


revision: str = "add_manager_oa_user_id_to_employee"
down_revision = "add_is_default_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scm_employee",
        sa.Column("manager_oa_user_id", sa.String(64), nullable=True, comment="上级人员OA用户ID"),
    )


def downgrade() -> None:
    op.drop_column("scm_employee", "manager_oa_user_id")
