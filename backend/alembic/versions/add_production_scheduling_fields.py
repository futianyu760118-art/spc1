"""add production scheduling fields

Revision ID: add_production_scheduling_fields
Revises: add_oa_position_id_to_position
Create Date: 2026-06-18 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_production_scheduling_fields"
down_revision: Union[str, Sequence[str], None] = "add_oa_position_id_to_position"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 产品表添加upph字段
    op.execute("ALTER TABLE scm_product ADD COLUMN IF NOT EXISTS upph NUMERIC(15, 2) DEFAULT 0 COMMENT '每小时产能UPPH'")
    
    # 2. 计划排产表添加上pph和daily_work_hours字段
    op.execute("ALTER TABLE production_schedule_plan ADD COLUMN IF NOT EXISTS upph NUMERIC(15, 2) DEFAULT 0 COMMENT '排产时使用的UPPH'")
    op.execute("ALTER TABLE production_schedule_plan ADD COLUMN IF NOT EXISTS daily_work_hours NUMERIC(5, 2) DEFAULT 8 COMMENT '每日工作小时数'")
    
    # 3. 初始化工作时间配置到node_standard表（如果不存在）
    op.execute(
        """
        INSERT INTO node_standard (node_code, node_name, time_value, time_unit, applicable_scene, description, is_active, created_by, created_at, updated_at)
        SELECT 'daily_work_hours', '每日工作小时数', 8, '小时', 'production_scheduling', '精益车间每日工作小时数，用于排产计算', true, 'system', now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM node_standard WHERE node_code = 'daily_work_hours')
        """
    )


def downgrade() -> None:
    # 1. 删除产品表upph字段
    op.execute("ALTER TABLE scm_product DROP COLUMN IF EXISTS upph")
    
    # 2. 删除计划排产表字段
    op.execute("ALTER TABLE production_schedule_plan DROP COLUMN IF EXISTS upph")
    op.execute("ALTER TABLE production_schedule_plan DROP COLUMN IF EXISTS daily_work_hours")
    
    # 3. 删除工作时间配置
    op.execute("DELETE FROM node_standard WHERE node_code = 'daily_work_hours'")
