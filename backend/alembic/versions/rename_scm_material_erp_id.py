"""rename scm_material.material_id to erp_material_id (int)

Revision ID: rename_scm_material_erp_id
Revises: merge_heads_20260629
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'rename_scm_material_erp_id'
down_revision: Union[str, None] = 'merge_heads_20260629'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scm_material ALTER COLUMN material_id "
        "TYPE INTEGER USING material_id::integer"
    )
    op.execute(
        "ALTER TABLE scm_material RENAME COLUMN material_id TO erp_material_id"
    )
    op.execute(
        "ALTER TABLE scm_material ALTER COLUMN parent_id "
        "TYPE INTEGER USING parent_id::integer"
    )
    op.execute(
        "ALTER TABLE scm_bom ALTER COLUMN material_id "
        "TYPE INTEGER USING material_id::integer"
    )
    op.execute(
        "ALTER TABLE scm_bom_detail ALTER COLUMN material_id "
        "TYPE INTEGER USING material_id::integer"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE scm_material RENAME COLUMN erp_material_id TO material_id"
    )
    op.execute(
        "ALTER TABLE scm_material ALTER COLUMN material_id "
        "TYPE VARCHAR(50) USING material_id::text"
    )
    op.execute(
        "ALTER TABLE scm_material ALTER COLUMN parent_id "
        "TYPE VARCHAR(50) USING parent_id::text"
    )
    op.execute(
        "ALTER TABLE scm_bom ALTER COLUMN material_id "
        "TYPE VARCHAR(50) USING material_id::text"
    )
    op.execute(
        "ALTER TABLE scm_bom_detail ALTER COLUMN material_id "
        "TYPE VARCHAR(50) USING material_id::text"
    )
