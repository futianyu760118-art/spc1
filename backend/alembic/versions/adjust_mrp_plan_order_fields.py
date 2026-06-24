"""adjust mrp_plan_order fields and composite primary key

Revision ID: adjust_mrp_plan_order_fields
Revises: add_sys_permission_table
Create Date: 2026-06-23 12:00:00.000000

说明：
    按 PRD 调整 MRP 计划订单表字段结构：
    - 移除原 fbill_no/fmaterial_id/fplan_qty/fplan_start_date/fplan_finish_date/
      fneed_date/forder_type/fstatus/fsupply_org/frequire_org/fsource_bill_no/data_source/id 等字段
    - 新增销售订单号、物料ID、单位ID、单位名称、基本单位计划订单量、MRP运算时间、
      业务关闭状态、关闭类型、销售订单ID、单据类型等字段
    - 主键由自增 id + fbill_no 唯一约束，改为 (sale_order_id, material_id) 联合主键
    - 旧表由 7314cacebdb6 / 80ec41a78266 迁移创建，此处统一 DROP 后重建（表为新建，无业务数据）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'adjust_mrp_plan_order_fields'
down_revision: Union[str, None] = 'add_sys_permission_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 旧表可能由 7314cacebdb6 或 80ec41a78266 创建，统一删除后重建
    op.execute("DROP TABLE IF EXISTS mrp_plan_order")

    op.create_table(
        'mrp_plan_order',
        sa.Column('sale_order_id', sa.Integer(), nullable=False, comment='销售订单ID'),
        sa.Column('material_id', sa.String(length=50), nullable=False, comment='物料ID'),
        sa.Column('sale_order_no', sa.String(length=64), nullable=True, comment='销售订单号'),
        sa.Column('material_code', sa.String(length=64), nullable=False, comment='物料代码'),
        sa.Column('material_name', sa.String(length=256), nullable=True, comment='物料名称'),
        sa.Column('unit_id', sa.String(length=50), nullable=True, comment='单位ID'),
        sa.Column('unit_name', sa.String(length=64), nullable=True, comment='单位名称'),
        sa.Column('base_plan_qty', sa.Numeric(precision=15, scale=2), nullable=True, comment='基本单位计划订单量'),
        sa.Column('mrp_run_time', sa.DateTime(), nullable=True, comment='MRP运算时间'),
        sa.Column('need_date', sa.Date(), nullable=True, comment='需求日期'),
        sa.Column('is_closed', sa.Integer(), nullable=False, server_default='0', comment='业务关闭状态 1-已关闭 0-未关闭'),
        sa.Column('close_type', sa.Integer(), nullable=True, comment='关闭类型 0-投放关闭'),
        sa.Column('bill_type', sa.Integer(), nullable=True, comment='单据类型 11010-采购申请 11011-自制生产任务单 11012-委外申请'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('sale_order_id', 'material_id', name='pk_mrp_plan_order'),
    )
    op.create_index('ix_mrp_plan_order_material_code', 'mrp_plan_order', ['material_code'], unique=False)
    op.create_index('ix_mrp_plan_order_sale_order_no', 'mrp_plan_order', ['sale_order_no'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_mrp_plan_order_sale_order_no', table_name='mrp_plan_order')
    op.drop_index('ix_mrp_plan_order_material_code', table_name='mrp_plan_order')
    op.drop_table('mrp_plan_order')

    # 回滚至 7314cacebdb6 版本的表结构
    op.create_table(
        'mrp_plan_order',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('fbill_no', sa.String(length=64), nullable=False, comment='计划订单号'),
        sa.Column('fmaterial_id', sa.Integer(), nullable=True, comment='物料内码'),
        sa.Column('material_code', sa.String(length=64), nullable=False, comment='物料代码'),
        sa.Column('material_name', sa.String(length=256), nullable=True, comment='物料名称'),
        sa.Column('fplan_qty', sa.Numeric(precision=15, scale=2), nullable=True, comment='计划数量'),
        sa.Column('fplan_start_date', sa.Date(), nullable=True, comment='计划开始日期'),
        sa.Column('fplan_finish_date', sa.Date(), nullable=True, comment='计划完工日期'),
        sa.Column('fneed_date', sa.Date(), nullable=True, comment='需求日期'),
        sa.Column('forder_type', sa.String(length=32), nullable=True, comment='订单类型(采购/生产/委外)'),
        sa.Column('fstatus', sa.Integer(), nullable=False, comment='状态(0=计划,1=已下达,2=已关闭,3=已作废)'),
        sa.Column('fsupply_org', sa.String(length=128), nullable=True, comment='供应组织'),
        sa.Column('frequire_org', sa.String(length=128), nullable=True, comment='需求组织'),
        sa.Column('fsource_bill_no', sa.String(length=64), nullable=True, comment='源单号'),
        sa.Column('data_source', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fbill_no', name='uq_mrp_plan_order_fbill_no'),
    )
    op.create_index(op.f('ix_mrp_plan_order_fbill_no'), 'mrp_plan_order', ['fbill_no'], unique=False)
    op.create_index(op.f('ix_mrp_plan_order_material_code'), 'mrp_plan_order', ['material_code'], unique=False)
