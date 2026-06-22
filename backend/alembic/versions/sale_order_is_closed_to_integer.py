"""sale_order.is_closed boolean -> integer

Revision ID: sale_order_is_closed_to_int
Revises: add_is_closed_to_purchase_order
Create Date: 2026-06-18 10:00:00.000000

说明：将 sale_order.is_closed 由 BOOLEAN 改为 INTEGER(0/1)，
与 purchase_order.is_closed 保持一致。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'sale_order_is_closed_to_int'
down_revision: Union[str, None] = 'add_is_closed_to_purchase_order'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE sale_order ALTER COLUMN is_closed TYPE integer USING is_closed::integer")
    op.execute("ALTER TABLE sale_order ALTER COLUMN is_closed SET DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE sale_order ALTER COLUMN is_closed TYPE boolean USING is_closed::boolean")
    op.execute("ALTER TABLE sale_order ALTER COLUMN is_closed SET DEFAULT false")
