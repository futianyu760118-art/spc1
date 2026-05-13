"""refactor long_lead_material: drop material_name/lead_time_days, add po_date to purchase_order

Revision ID: refactor_long_lead
Revises: fix_sale_order_unique_index
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'refactor_long_lead'
down_revision = 'fix_sale_order_unique_index'
branch_labels = None
depends_on = None


def upgrade():
    # Drop columns from long_lead_material (now a pure annotation table)
    op.drop_column('long_lead_material', 'material_name')
    op.drop_column('long_lead_material', 'lead_time_days')


def downgrade():
    # Re-add columns
    op.add_column('long_lead_material', sa.Column('material_name', sa.String(256), nullable=True))
    op.add_column('long_lead_material', sa.Column('lead_time_days', sa.Integer(), nullable=True))
