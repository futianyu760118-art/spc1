"""fix sale_order order_no index: drop unique, recreate non-unique

Revision ID: fix_order_no_idx
Revises: add_sync_config
Create Date: 2026-04-17 17:10:00.000000

"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'fix_order_no_idx'
down_revision: Union[str, None] = 'add_sync_config'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop stale FK from sale_order_line that depends on the unique index
    op.execute("ALTER TABLE sale_order_line DROP CONSTRAINT IF EXISTS sale_order_line_order_no_fkey")
    # Drop the old unique index
    op.execute("DROP INDEX IF EXISTS ix_sale_order_order_no CASCADE")
    # Recreate as a plain non-unique index
    op.create_index('ix_sale_order_order_no', 'sale_order', ['order_no'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_sale_order_order_no', table_name='sale_order')
    op.create_index('ix_sale_order_order_no', 'sale_order', ['order_no'], unique=True)
