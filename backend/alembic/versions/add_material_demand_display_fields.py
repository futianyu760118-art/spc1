"""add material demand display fields

Revision ID: add_md_display_fields
Revises: add_po_material_property
Create Date: 2026-06-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_md_display_fields"
down_revision: Union[str, Sequence[str], None] = "add_po_material_property"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("material_demand", sa.Column("material_property", sa.Integer(), nullable=True, comment="物料属性"))
    op.add_column("material_demand", sa.Column("material_type_name", sa.String(length=64), nullable=True, comment="物料分类"))
    op.add_column("material_demand", sa.Column("spec_model", sa.String(length=256), nullable=True, comment="规格型号"))
    op.add_column("material_demand", sa.Column("unit", sa.String(length=32), nullable=True, comment="单位"))


def downgrade() -> None:
    op.drop_column("material_demand", "unit")
    op.drop_column("material_demand", "spec_model")
    op.drop_column("material_demand", "material_type_name")
    op.drop_column("material_demand", "material_property")
