"""add_data_supply_tables

Revision ID: de5c568cde8c
Revises: 6446605a9660
Create Date: 2026-06-23 15:23:23.065834
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'de5c568cde8c'
down_revision: Union[str, None] = '6446605a9660'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('data_supply_config',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('data_type', sa.String(length=64), nullable=False, comment='数据实体标识 (customers/suppliers/...)'),
    sa.Column('data_name', sa.String(length=128), nullable=False, comment='数据实体中文名'),
    sa.Column('description', sa.String(length=512), nullable=True, comment='描述'),
    sa.Column('model_name', sa.String(length=128), nullable=False, comment='对应 SQLAlchemy 模型类名'),
    sa.Column('allowed_fields_json', sa.Text(), nullable=True, comment='允许暴露的字段列表 JSON'),
    sa.Column('filter_fields_json', sa.Text(), nullable=True, comment='允许作为筛选条件的字段列表 JSON'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('data_type')
    )

    op.create_table('data_supply_api_key',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key_name', sa.String(length=128), nullable=False, comment='Key 名称（通常为外部系统名）'),
    sa.Column('api_key', sa.String(length=64), nullable=False, comment='API Key 值'),
    sa.Column('description', sa.String(length=512), nullable=True, comment='用途说明'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('allowed_data_types_json', sa.Text(), nullable=True, comment='允许访问的数据类型列表 JSON'),
    sa.Column('rate_limit', sa.Integer(), nullable=True, comment='每分钟请求限制'),
    sa.Column('expires_at', sa.DateTime(), nullable=True, comment='过期时间（null 表示永不过期）'),
    sa.Column('created_by', sa.String(length=64), nullable=True, comment='创建人'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_data_supply_api_key_api_key'), 'data_supply_api_key', ['api_key'], unique=True)

    op.create_table('data_supply_call_log',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('api_key_id', sa.Integer(), nullable=True, comment='关联 API Key ID'),
    sa.Column('api_key_name', sa.String(length=128), nullable=True, comment='API Key 名称快照'),
    sa.Column('data_type', sa.String(length=64), nullable=False, comment='请求的数据类型'),
    sa.Column('request_params_json', sa.Text(), nullable=True, comment='请求参数快照'),
    sa.Column('response_status', sa.Integer(), nullable=True, comment='HTTP 响应状态码'),
    sa.Column('response_count', sa.Integer(), nullable=True, comment='返回数据条数'),
    sa.Column('ip_address', sa.String(length=64), nullable=True, comment='请求来源 IP'),
    sa.Column('user_agent', sa.String(length=256), nullable=True, comment='请求 User-Agent'),
    sa.Column('duration_ms', sa.Numeric(precision=10, scale=2), nullable=True, comment='响应耗时(ms)'),
    sa.Column('called_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_data_supply_call_log_api_key_id'), 'data_supply_call_log', ['api_key_id'], unique=False)
    op.create_index(op.f('ix_data_supply_call_log_called_at'), 'data_supply_call_log', ['called_at'], unique=False)
    op.create_index(op.f('ix_data_supply_call_log_data_type'), 'data_supply_call_log', ['data_type'], unique=False)


def downgrade() -> None:
    op.drop_table('data_supply_call_log')
    op.drop_table('data_supply_api_key')
    op.drop_table('data_supply_config')
