"""fix_scm_id_columns_to_integer

Revision ID: fix_scm_id_columns_to_integer
Revises: None
Create Date: 2026-07-08

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'fix_scm_id_columns_to_integer'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # scm_location: location_id, location_group_id, parent_id 从 VARCHAR 转为 INTEGER
    op.execute("ALTER TABLE scm_location ALTER COLUMN location_id TYPE INTEGER USING location_id::integer")
    op.execute("ALTER TABLE scm_location ALTER COLUMN location_group_id TYPE INTEGER USING location_group_id::integer")
    op.execute("ALTER TABLE scm_location ALTER COLUMN parent_id TYPE INTEGER USING parent_id::integer")

    # scm_warehouse: wh_id, parent_wh_id 从 VARCHAR 转为 INTEGER
    op.execute("ALTER TABLE scm_warehouse ALTER COLUMN wh_id TYPE INTEGER USING wh_id::integer")
    op.execute("ALTER TABLE scm_warehouse ALTER COLUMN parent_wh_id TYPE INTEGER USING parent_wh_id::integer")

    # scm_inventory: material_id, wh_id, location_id 从 VARCHAR 转为 INTEGER
    op.execute("ALTER TABLE scm_inventory ALTER COLUMN material_id TYPE INTEGER USING material_id::integer")
    op.execute("ALTER TABLE scm_inventory ALTER COLUMN wh_id TYPE INTEGER USING wh_id::integer")
    op.execute("ALTER TABLE scm_inventory ALTER COLUMN location_id TYPE INTEGER USING location_id::integer")


def downgrade() -> None:
    # 回滚: INTEGER 转回 VARCHAR
    op.execute("ALTER TABLE scm_location ALTER COLUMN location_id TYPE VARCHAR(50) USING location_id::text")
    op.execute("ALTER TABLE scm_location ALTER COLUMN location_group_id TYPE VARCHAR(50) USING location_group_id::text")
    op.execute("ALTER TABLE scm_location ALTER COLUMN parent_id TYPE VARCHAR(50) USING parent_id::text")

    op.execute("ALTER TABLE scm_warehouse ALTER COLUMN wh_id TYPE VARCHAR(50) USING wh_id::text")
    op.execute("ALTER TABLE scm_warehouse ALTER COLUMN parent_wh_id TYPE VARCHAR(50) USING parent_wh_id::text")

    op.execute("ALTER TABLE scm_inventory ALTER COLUMN material_id TYPE VARCHAR(50) USING material_id::text")
    op.execute("ALTER TABLE scm_inventory ALTER COLUMN wh_id TYPE VARCHAR(50) USING wh_id::text")
    op.execute("ALTER TABLE scm_inventory ALTER COLUMN location_id TYPE VARCHAR(50) USING location_id::text")
