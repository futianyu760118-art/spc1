"""add rules config tables

Revision ID: add_rules_config
Revises: c5d3e8f92b04
Create Date: 2026-04-17 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_rules_config'
down_revision: Union[str, None] = 'add_condition_params'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 先删除可能存在的不完整表
    op.drop_table('inspection_rule', if_exists=True)
    op.drop_table('node_standard', if_exists=True)
    op.drop_table('responsibility_map', if_exists=True)
    op.drop_table('status_dictionary', if_exists=True)

    # 点检规则表
    op.create_table(
        'inspection_rule',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('module_code', sa.String(32), nullable=False, comment='所属模块'),
        sa.Column('rule_type', sa.String(32), nullable=False, comment='规则类型'),
        sa.Column('item_code', sa.String(64), nullable=False, unique=True, comment='点检项编码'),
        sa.Column('item_name', sa.String(128), nullable=False, comment='点检项名称'),
        sa.Column('parent_code', sa.String(64), nullable=True, comment='父级编码'),
        sa.Column('standard_desc', sa.Text(), nullable=True, comment='标准说明'),
        sa.Column('sort_order', sa.Integer(), nullable=True, default=0, comment='排序号'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        comment='点检规则配置表'
    )

    # 节点标准表
    op.create_table(
        'node_standard',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('node_code', sa.String(64), nullable=False, unique=True, comment='节点编码'),
        sa.Column('node_name', sa.String(128), nullable=False, comment='节点名称'),
        sa.Column('time_value', sa.Integer(), nullable=False, comment='标准值'),
        sa.Column('time_unit', sa.String(16), nullable=False, default='天', comment='单位'),
        sa.Column('applicable_scene', sa.String(64), nullable=False, comment='适用场景'),
        sa.Column('description', sa.String(256), nullable=True, comment='描述'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        comment='节点标准配置表'
    )

    # 责任归属表
    op.create_table(
        'responsibility_map',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_item_code', sa.String(64), nullable=False, comment='关联点检规则编码'),
        sa.Column('department', sa.String(64), nullable=False, comment='责任部门'),
        sa.Column('role_name', sa.String(64), nullable=False, comment='责任角色'),
        sa.Column('user_id', sa.String(64), nullable=True, comment='具体用户ID'),
        sa.Column('user_name', sa.String(64), nullable=True, comment='具体用户名'),
        sa.Column('escalation_level', sa.Integer(), nullable=True, default=0, comment='升级层级'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        comment='责任归属配置表'
    )

    # 状态字典表
    op.create_table(
        'status_dictionary',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('status_type', sa.String(64), nullable=False, comment='状态类型'),
        sa.Column('code', sa.String(32), nullable=False, comment='状态代码'),
        sa.Column('name', sa.String(64), nullable=False, comment='状态名称'),
        sa.Column('color_tag', sa.String(32), nullable=False, comment='颜色标签'),
        sa.Column('display_color', sa.String(16), nullable=True, comment='显示颜色值'),
        sa.Column('sort_order', sa.Integer(), nullable=True, default=0, comment='排序号'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        comment='状态字典配置表'
    )

    # 创建索引
    op.create_index('ix_inspection_rule_module_code', 'inspection_rule', ['module_code'])
    op.create_index('ix_inspection_rule_item_code', 'inspection_rule', ['item_code'])
    op.create_index('ix_node_standard_node_code', 'node_standard', ['node_code'])
    op.create_index('ix_node_standard_applicable_scene', 'node_standard', ['applicable_scene'])
    op.create_index('ix_responsibility_map_rule_item_code', 'responsibility_map', ['rule_item_code'])
    op.create_index('ix_responsibility_map_department', 'responsibility_map', ['department'])
    op.create_index('ix_status_dictionary_status_type', 'status_dictionary', ['status_type'])


def downgrade() -> None:
    # 删除索引（使用if_exists避免错误）
    try:
        op.drop_index('ix_status_dictionary_status_type', 'status_dictionary')
    except:
        pass
    try:
        op.drop_index('ix_responsibility_map_department', 'responsibility_map')
    except:
        pass
    try:
        op.drop_index('ix_responsibility_map_rule_item_code', 'responsibility_map')
    except:
        pass
    try:
        op.drop_index('ix_node_standard_applicable_scene', 'node_standard')
    except:
        pass
    try:
        op.drop_index('ix_node_standard_node_code', 'node_standard')
    except:
        pass
    try:
        op.drop_index('ix_inspection_rule_item_code', 'inspection_rule')
    except:
        pass
    try:
        op.drop_index('ix_inspection_rule_module_code', 'inspection_rule')
    except:
        pass

    # 删除表（使用if_exists）
    op.drop_table('status_dictionary', if_exists=True)
    op.drop_table('responsibility_map', if_exists=True)
    op.drop_table('node_standard', if_exists=True)
    op.drop_table('inspection_rule', if_exists=True)
