"""add erp_user_id to scm_employee

Revision ID: 0111
Revises: 0110
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0111'
down_revision: Union[str, Sequence[str], None] = '0110'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 新增 erp_user_id 列：存放通过姓名匹配回填的 ERP 用户ID。
    # 不设唯一约束 —— 同名员工可能对应同一 ERP 用户；列可空以兼容未匹配上的员工。
    op.add_column(
        'scm_employee',
        sa.Column('erp_user_id', sa.BigInteger(), nullable=True, comment='ERP系统用户ID（通过姓名匹配回填）'),
    )


def downgrade() -> None:
    op.drop_column('scm_employee', 'erp_user_id')