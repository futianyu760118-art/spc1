"""stock check: per-bom-line items (level col, drop uq) + co-checkers

Revision ID: add_chk_level_and_cocheck
Revises: add_inv_check_covered
Create Date: 2026-07-22

说明：
- 订单盘点改为按 BOM 每条明细一行（不再按 material_id 聚合）：
  * scm_inventory_check_item 增加 level INTEGER（BOM 层级）。
  * 移除唯一约束 uq_stock_check_item (check_id,material_id,line_no)，
    因为同一物料在 BOM 多处出现时会有多行，旧约束会冲突。
- 盘点单增加共同盘点人/创建人标识：
  * scm_inventory_check 增加 co_checker_user_ids JSONB（sys_user.id 列表）
    与 created_by_user_id BIGINT。
- 使用 IF NOT EXISTS / IF EXISTS 幂等写法，与 init_database.py 风格一致。
  (项目以 init_database.py 为运行时真相源；Alembic 仅手动执行。)
- revision id 控制在 32 字符以内。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_chk_level_and_cocheck"
down_revision: Union[str, Sequence[str], None] = "add_inv_check_covered"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Req2: per-BOM-line items ---
    op.execute(
        "ALTER TABLE scm_inventory_check_item "
        "ADD COLUMN IF NOT EXISTS level INTEGER"
    )
    op.execute(
        "ALTER TABLE scm_inventory_check_item "
        "DROP CONSTRAINT IF EXISTS uq_stock_check_item"
    )
    # --- Req3: co-checkers ---
    op.execute(
        "ALTER TABLE scm_inventory_check "
        "ADD COLUMN IF NOT EXISTS co_checker_user_ids JSONB"
    )
    op.execute(
        "ALTER TABLE scm_inventory_check "
        "ADD COLUMN IF NOT EXISTS created_by_user_id BIGINT"
    )
    op.execute(
        "COMMENT ON COLUMN scm_inventory_check.co_checker_user_ids IS "
        "'共同盘点人 sys_user.id 列表'"
    )
    op.execute(
        "COMMENT ON COLUMN scm_inventory_check.created_by_user_id IS "
        "'创建人 sys_user.id（用于修改权限判定）'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scm_inventory_check DROP COLUMN IF EXISTS created_by_user_id")
    op.execute("ALTER TABLE scm_inventory_check DROP COLUMN IF EXISTS co_checker_user_ids")
    op.execute(
        "ALTER TABLE scm_inventory_check_item "
        "ADD CONSTRAINT IF NOT EXISTS uq_stock_check_item "
        "UNIQUE (check_id, material_id, line_no)"
    )
    op.execute("ALTER TABLE scm_inventory_check_item DROP COLUMN IF EXISTS level")
