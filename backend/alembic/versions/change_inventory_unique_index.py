"""change scm_inventory unique index to (material_id, wh_id, location_id)

Revision ID: chg_inventory_uq
Revises: add_pi_payment_order_id
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'chg_inventory_uq'
down_revision: Union[str, None] = 'add_pi_payment_order_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('uq_inventory_material_wh_location', 'scm_inventory', type_='unique')

    op.alter_column('scm_inventory', 'material_id',
                     existing_type=sa.Integer(),
                     nullable=False)
    op.alter_column('scm_inventory', 'wh_id',
                     existing_type=sa.Integer(),
                     nullable=False)
    op.alter_column('scm_inventory', 'material_code',
                     existing_type=sa.String(length=50),
                     nullable=True)
    op.alter_column('scm_inventory', 'wh_code',
                     existing_type=sa.String(length=20),
                     nullable=True)

    op.create_unique_constraint(
        'uq_inventory_material_wh_location',
        'scm_inventory',
        ['material_id', 'wh_id', 'location_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_inventory_material_wh_location', 'scm_inventory', type_='unique')

    op.alter_column('scm_inventory', 'material_id',
                     existing_type=sa.Integer(),
                     nullable=True)
    op.alter_column('scm_inventory', 'wh_id',
                     existing_type=sa.Integer(),
                     nullable=True)
    op.alter_column('scm_inventory', 'material_code',
                     existing_type=sa.String(length=50),
                     nullable=False)
    op.alter_column('scm_inventory', 'wh_code',
                     existing_type=sa.String(length=20),
                     nullable=False)

    op.create_unique_constraint(
        'uq_inventory_material_wh_location',
        'scm_inventory',
        ['material_code', 'wh_code', 'location_id'],
    )
