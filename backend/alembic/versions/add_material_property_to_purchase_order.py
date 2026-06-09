"""add material_property to purchase_order

Revision ID: add_po_material_property
Revises: add_product_model
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_po_material_property'
down_revision = 'add_product_model'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('purchase_order', sa.Column('material_property', sa.Integer(), nullable=True, comment='物料属性'))


def downgrade() -> None:
    op.drop_column('purchase_order', 'material_property')
