"""add topbar permissions

Revision ID: add_topbar_permissions
Revises: seed_normal_order_standards
Create Date: 2026-06-09 00:00:00.000000
"""
import json
from typing import Sequence, Union

from alembic import op


revision: str = "add_topbar_permissions"
down_revision: Union[str, Sequence[str], None] = "seed_normal_order_standards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INTERNAL_TOPBAR_PERMISSIONS = {
    "topbar.share": ["read"],
    "topbar.feedback": ["read"],
    "topbar.ai_search": ["read"],
    "topbar.font_size": ["read"],
    "topbar.notifications": ["read"],
}

SUPPLIER_TOPBAR_PERMISSIONS = {
    "topbar.font_size": ["read"],
    "topbar.notifications": ["read"],
}


def upgrade() -> None:
    internal_permissions = json.dumps(INTERNAL_TOPBAR_PERMISSIONS, ensure_ascii=False)
    supplier_permissions = json.dumps(SUPPLIER_TOPBAR_PERMISSIONS, ensure_ascii=False)

    op.execute(
        f"""
        UPDATE sys_role
        SET permissions = COALESCE(permissions, '{{}}'::jsonb) || '{internal_permissions}'::jsonb
        WHERE role_code IN ('admin', 'planner', 'purchaser', 'manager', 'purchase_manager')
        """
    )
    op.execute(
        f"""
        UPDATE sys_role
        SET permissions = COALESCE(permissions, '{{}}'::jsonb) || '{supplier_permissions}'::jsonb
        WHERE role_code = 'supplier'
        """
    )


def downgrade() -> None:
    keys = [
        "topbar.share",
        "topbar.feedback",
        "topbar.ai_search",
        "topbar.font_size",
        "topbar.notifications",
    ]
    expression = "permissions"
    for key in keys:
        expression = f"({expression} - '{key}')"

    op.execute(
        f"""
        UPDATE sys_role
        SET permissions = {expression}
        WHERE role_code IN ('admin', 'planner', 'purchaser', 'manager', 'purchase_manager', 'supplier')
        """
    )
