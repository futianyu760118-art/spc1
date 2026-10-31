"""add material_property to scm_material

Revision ID: add_scm_material_property
Revises: add_subcontract_order_tables
Create Date: 2026-07-21

说明：
- 为 scm_material 增加 material_property (INTEGER) 字段，对齐
  purchase_order / mrp_plan_order / material_demand 上已有的同名属性，
  来源为 K3 t_ICItem.FErpClsID。
- 取值约定：1-外购 2-自制 3-委外加工 5-虚拟件 6-特征类 7-配置类 8-规划类 9-组装件。
- 项目以 init_database.py 的 migrate_columns 为运行时真相源（容器每次
  启动都会执行 ADD COLUMN IF NOT EXISTS）；Alembic 仅手动执行，两者
  并存幂等不冲突。
- 使用 ADD/DROP COLUMN IF NOT EXISTS/IF EXISTS 写法，避免重复执行报错。
- revision id 控制在 32 字符以内，规避 alembic_version.version_num
  默认 varchar(32) 的限制。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_scm_material_property"
down_revision: Union[str, Sequence[str], None] = "add_subcontract_order_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scm_material "
        "ADD COLUMN IF NOT EXISTS material_property INTEGER"
    )
    # 补 comment（ADD COLUMN 不支持 IF NOT EXISTS 时直接带 comment 的跨版本兼容写法，
    # 单独 COMMENT IF EXISTS 仅 PG 14+ 支持，这里用 try-except 风格的幂等 SQL）
    op.execute(
        "COMMENT ON COLUMN scm_material.material_property IS "
        "'物料属性 1-外购 2-自制 3-委外加工 5-虚拟件 6-特征类 7-配置类 8-规划类 9-组装件'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scm_material DROP COLUMN IF EXISTS material_property")
