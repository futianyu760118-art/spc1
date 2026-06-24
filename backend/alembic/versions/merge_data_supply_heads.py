"""merge heads before data_supply upgrade

Revision ID: merge_data_supply_heads
Revises: add_app_key_fields_data_supply, add_mrp_plan_order_material_type
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = 'merge_data_supply_heads'
down_revision = ('add_app_key_fields_data_supply', 'add_mrp_plan_order_material_type')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
