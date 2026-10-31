"""add supplier name to sys_user

Revision ID: add_supplier_name_to_sys_user
Revises: add_permissions_to_share_link
Create Date: 2026-06-09 00:00:00.000000
"""
import json
from typing import Sequence, Union

from alembic import op


revision: str = "add_supplier_name_to_sys_user"
down_revision: Union[str, Sequence[str], None] = "add_permissions_to_share_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPPLIER_PERMISSIONS = {
    "materials.purchase_plan": ["read"],
    "materials.long_lead": ["read"],
    "materials.supplier_risk": ["read"],
    "materials.supplier_payment": ["read"],
}


def upgrade() -> None:
    op.execute("ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS supplier_name VARCHAR(100)")
    op.execute(
        """
        INSERT INTO sys_role (role_code, role_name, permissions)
        VALUES (
            'supplier',
            '\u4f9b\u5e94\u5546',
            '{permissions}'::jsonb
        )
        ON CONFLICT (role_code) DO UPDATE
        SET role_name = EXCLUDED.role_name,
            permissions = EXCLUDED.permissions
        """.format(permissions=json.dumps(SUPPLIER_PERMISSIONS, ensure_ascii=False))
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sys_user DROP COLUMN IF EXISTS supplier_name")
