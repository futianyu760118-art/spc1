"""add material_property to mrp_plan_order

Revision ID: add_mrp_plan_order_material_property
Revises: de5c568cde8c
Create Date: 2026-06-23 16:00:00.000000

说明：
    为 MRP 计划订单新增 物料属性 字段（来源 K3 t_ICItem.FErpClsID），
    用于齐套分析展开行直接展示计划订单的物料属性。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_mrp_plan_mat_property'
down_revision: Union[str, None] = 'de5c568cde8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'mrp_plan_order',
        sa.Column(
            'material_property',
            sa.Integer(),
            nullable=True,
            comment='物料属性 1-外购 2-自制 3-委外加工 5-虚拟件 6-特征类 7-配置类 8-规划类 9-组装件',
        ),
    )
    # 历史数据回填：按单据类型推导物料属性（后续 ERP 同步会用 K3 FErpClsID 精确覆盖）
    op.execute(
        "UPDATE mrp_plan_order SET material_property = CASE bill_type "
        "WHEN 11010 THEN 1 WHEN 11011 THEN 2 WHEN 11012 THEN 3 ELSE 1 END "
        "WHERE material_property IS NULL"
    )


def downgrade() -> None:
    op.drop_column('mrp_plan_order', 'material_property')
