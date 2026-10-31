"""add org_id and position_id to sys_role

Revision ID: add_org_position_to_sys_role
Revises: add_qi_erp_quality_id
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_org_position_to_sys_role'
down_revision: Union[str, Sequence[str], None] = ('add_qi_erp_quality_id', 'add_manager_oa_user_id_to_employee')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sys_role', sa.Column('org_id', sa.BigInteger(), nullable=True, comment='关联部门ID'))
    op.add_column('sys_role', sa.Column('position_id', sa.BigInteger(), nullable=True, comment='关联岗位ID'))


def downgrade() -> None:
    op.drop_column('sys_role', 'position_id')
    op.drop_column('sys_role', 'org_id')
