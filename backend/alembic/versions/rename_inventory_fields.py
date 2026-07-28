"""rename qty_available->locked_qty, qty_reserved->balance_qty on scm_inventory

Revision ID: rename_inventory_fields
Revises: chg_inventory_uq
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'rename_inventory_fields'
down_revision: Union[str, None] = '0101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('scm_inventory', 'qty_available', new_column_name='locked_qty',
                     existing_type=sa.Numeric(15, 2), existing_nullable=False,
                     existing_server_default=sa.text('0'))
    op.alter_column('scm_inventory', 'qty_reserved', new_column_name='balance_qty',
                     existing_type=sa.Numeric(15, 2), existing_nullable=False,
                     existing_server_default=sa.text('0'))


def downgrade() -> None:
    op.alter_column('scm_inventory', 'locked_qty', new_column_name='qty_available',
                     existing_type=sa.Numeric(15, 2), existing_nullable=False,
                     existing_server_default=sa.text('0'))
    op.alter_column('scm_inventory', 'balance_qty', new_column_name='qty_reserved',
                     existing_type=sa.Numeric(15, 2), existing_nullable=False,
                     existing_server_default=sa.text('0'))
