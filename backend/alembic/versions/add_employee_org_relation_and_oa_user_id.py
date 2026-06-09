"""add employee_org_relation and oa_user_id

Revision ID: add_employee_org_relation_oa_user_id
Revises: add_middle_platform_modules
Create Date: 2026-06-05 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_employee_org_relation_oa_user_id"
down_revision: Union[str, None] = "add_middle_platform_modules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. scm_employee 表添加 oa_user_id 字段
    op.add_column("scm_employee", sa.Column("oa_user_id", sa.String(length=64), nullable=True, comment="OA系统用户ID"))
    op.create_unique_constraint("uq_scm_employee_oa_user_id", "scm_employee", ["oa_user_id"])

    # 2. scm_employee 表 org_id 改为 nullable
    op.alter_column("scm_employee", "org_id", existing_type=sa.BigInteger(), nullable=True)

    # 3. 创建 scm_employee_organization 关联表
    op.create_table(
        "scm_employee_organization",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("emp_code", sa.String(length=20), nullable=False, comment="员工工号"),
        sa.Column("org_code", sa.String(length=20), nullable=False, comment="组织编码"),
        sa.Column("is_primary", sa.Integer(), nullable=False, server_default="0", comment="是否主部门 (1-是 0-否)"),
        sa.Column("position", sa.String(length=50), nullable=True, comment="在该部门的岗位"),
        sa.Column("status", sa.Integer(), nullable=False, server_default="1", comment="状态"),
        sa.Column("data_source", sa.String(length=32), nullable=True),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("emp_code", "org_code", name="uq_emp_org_code"),
    )


def downgrade() -> None:
    op.drop_table("scm_employee_organization")
    op.alter_column("scm_employee", "org_id", existing_type=sa.BigInteger(), nullable=False)
    op.drop_constraint("uq_scm_employee_oa_user_id", "scm_employee", type_="unique")
    op.drop_column("scm_employee", "oa_user_id")
