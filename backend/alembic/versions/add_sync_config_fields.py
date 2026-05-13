"""add sync config fields to sync_sql_config

Revision ID: add_sync_config
Revises: add_masterdata_tables
Create Date: 2026-04-17 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_sync_config'
down_revision: Union[str, None] = 'add_masterdata_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加同步配置字段
    op.add_column('sync_sql_config', sa.Column('sync_interval', sa.String(length=20), nullable=False, server_default='1h', comment='同步间隔 (1h/2h/6h/12h/1d/1w)'))
    op.add_column('sync_sql_config', sa.Column('sync_strategy', sa.String(length=20), nullable=False, server_default='incremental', comment='同步策略 (incremental/full/hybrid)'))
    op.add_column('sync_sql_config', sa.Column('sync_time_window', sa.String(length=50), nullable=True, comment='同步时间窗口 (如: 02:00-04:00 或 null表示不限)'))
    op.add_column('sync_sql_config', sa.Column('sync_priority', sa.Integer(), nullable=False, server_default=5, comment='同步优先级 (1-10, 数字越小优先级越高)'))
    op.add_column('sync_sql_config', sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default=True, comment='是否启用同步'))
    
    # 添加同步时间跟踪字段
    op.add_column('sync_sql_config', sa.Column('last_sync_time', sa.DateTime(), nullable=True, comment='上次同步时间'))
    op.add_column('sync_sql_config', sa.Column('next_sync_time', sa.DateTime(), nullable=True, comment='下次计划同步时间'))
    op.add_column('sync_sql_config', sa.Column('last_sync_status', sa.String(length=20), nullable=True, comment='上次同步状态 (success/failed/running)'))
    op.add_column('sync_sql_config', sa.Column('last_sync_message', sa.Text(), nullable=True, comment='上次同步消息'))
    
    # 修改 sync_type 为唯一
    # 注意：如果已有重复的sync_type数据，需要先手动清理
    op.create_unique_constraint('uq_sync_sql_config_sync_type', 'sync_sql_config', ['sync_type'])
    
    # 更新 updated_at 字段，添加 onupdate
    op.alter_column('sync_sql_config', 'updated_at', server_default=sa.text('now()'), onupdate=sa.text('now()'))


def downgrade() -> None:
    # 删除同步时间跟踪字段
    op.drop_column('sync_sql_config', 'last_sync_message')
    op.drop_column('sync_sql_config', 'last_sync_status')
    op.drop_column('sync_sql_config', 'next_sync_time')
    op.drop_column('sync_sql_config', 'last_sync_time')
    
    # 删除同步配置字段
    op.drop_column('sync_sql_config', 'sync_enabled')
    op.drop_column('sync_sql_config', 'sync_priority')
    op.drop_column('sync_sql_config', 'sync_time_window')
    op.drop_column('sync_sql_config', 'sync_strategy')
    op.drop_column('sync_sql_config', 'sync_interval')
    
    # 删除唯一约束
    op.drop_constraint('uq_sync_sql_config_sync_type', 'sync_sql_config', type_='unique')
    
    # 恢复 updated_at 字段
    op.alter_column('sync_sql_config', 'updated_at', server_default=sa.text('now()'), onupdate=None)
