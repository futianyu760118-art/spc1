"""add allowed_endpoints_json to data_supply_api_key

Revision ID: add_allowed_endpoints_json
Revises: add_app_key_fields_data_supply
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_allowed_endpoints_json'
down_revision = 'merge_data_supply_heads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'data_supply_api_key',
        sa.Column('allowed_endpoints_json', sa.Text(), nullable=True, comment='允许调用的对外接口 endpoint_code 列表 JSON'),
    )


def downgrade() -> None:
    op.drop_column('data_supply_api_key', 'allowed_endpoints_json')
