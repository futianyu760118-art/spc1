"""add order_nature to sale_order

Revision ID: add_order_nature
Revises: fix_order_no_idx
Create Date: 2026-04-20 16:24:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_order_nature'
down_revision: Union[str, None] = 'fix_order_no_idx'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sale_order', sa.Column('order_nature', sa.String(32), nullable=True, comment='订单性质'))


def downgrade() -> None:
    op.drop_column('sale_order', 'order_nature')
