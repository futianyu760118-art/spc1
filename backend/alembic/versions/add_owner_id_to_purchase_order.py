"""add owner_id to purchase_order

Revision ID: add_owner_id_to_purchase_order
Revises: add_employee_org_relation_oa_user_id
Create Date: 2026-07-09 15:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_owner_id_to_purchase_order'
down_revision: Union[str, None] = 'add_employee_org_relation_oa_user_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_order', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'purchase_order', 'sys_user', ['owner_id'], ['id'])
    op.create_index(op.f('ix_purchase_order_owner_id'), 'purchase_order', ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_purchase_order_owner_id'), table_name='purchase_order')
    op.drop_constraint(None, 'purchase_order', type_='foreignkey')
    op.drop_column('purchase_order', 'owner_id')
