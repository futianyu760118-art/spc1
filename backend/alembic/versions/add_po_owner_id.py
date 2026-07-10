"""add owner_id column to purchase_order

Revision ID: add_po_owner_id
Revises: rename_inventory_fields
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_po_owner_id'
down_revision: Union[str, None] = 'rename_inventory_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_order',
                  sa.Column('owner_id', sa.Integer(), nullable=True, index=True))
    op.create_foreign_key('fk_po_owner_id_sys_user', 'purchase_order', 'sys_user', ['owner_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_po_owner_id_sys_user', 'purchase_order', type_='foreignkey')
    op.drop_column('purchase_order', 'owner_id')
