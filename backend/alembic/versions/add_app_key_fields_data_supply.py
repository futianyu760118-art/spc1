"""add app_key app_secret ip_whitelist mask_fields to data_supply

Revision ID: add_app_key_fields_data_supply
Revises: add_is_closed_to_sale_order
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_app_key_fields_data_supply'
down_revision = 'add_is_closed_to_sale_order'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # data_supply_api_key: 添加 app_key, app_secret, ip_whitelist_json
    op.add_column('data_supply_api_key', sa.Column('app_key', sa.String(64), nullable=True, comment='应用标识（AppKey）'))
    op.add_column('data_supply_api_key', sa.Column('app_secret', sa.String(128), nullable=True, comment='应用密钥（AppSecret）'))
    op.add_column('data_supply_api_key', sa.Column('ip_whitelist_json', sa.Text(), nullable=True, comment='IP 白名单 JSON 列表'))
    op.create_index('ix_data_supply_api_key_app_key', 'data_supply_api_key', ['app_key'], unique=True)

    # data_supply_config: 添加 mask_fields_json
    op.add_column('data_supply_config', sa.Column('mask_fields_json', sa.Text(), nullable=True, comment='需要脱敏的字段列表 JSON'))


def downgrade() -> None:
    op.drop_index('ix_data_supply_api_key_app_key', table_name='data_supply_api_key')
    op.drop_column('data_supply_api_key', 'ip_whitelist_json')
    op.drop_column('data_supply_api_key', 'app_secret')
    op.drop_column('data_supply_api_key', 'app_key')
    op.drop_column('data_supply_config', 'mask_fields_json')
