"""add orders.inventory_check permission to roles

Revision ID: 0101
Revises: 0100
Create Date: 2026-07-10
"""
from alembic import op
import json

revision = '0101'
down_revision = 'chg_inventory_uq'
branch_labels = None
depends_on = None


def upgrade():
    # Insert the permission into sys_permission (if not exists)
    conn = op.get_bind()
    exists = conn.execute(
        "SELECT 1 FROM sys_permission WHERE code = 'orders.inventory_check'"
    ).fetchone()
    if not exists:
        conn.execute("""
            INSERT INTO sys_permission (code, name, module, parent_code, actions, route_path, sort_order)
            VALUES ('orders.inventory_check', '订单物料盘点', 'orders', 'orders',
                    '["create","read","update","delete"]'::jsonb, '/inventory-check', 4)
        """)

    # Grant orders.inventory_check to all roles that already have orders.list
    # by copying the actions from orders.list
    conn.execute("""
        UPDATE sys_role
        SET permissions = permissions || jsonb_build_object(
            'orders.inventory_check',
            permissions -> 'orders.list'
        )
        WHERE permissions ? 'orders.list'
          AND NOT permissions ? 'orders.inventory_check'
    """)


def downgrade():
    conn = op.get_bind()
    conn.execute("""
        UPDATE sys_role
        SET permissions = permissions - 'orders.inventory_check'
    """)
    conn.execute("""
        DELETE FROM sys_permission WHERE code = 'orders.inventory_check'
    """)
