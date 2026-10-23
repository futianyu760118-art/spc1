"""user_ids_with_permission 与运行时权限口径一致。"""

from sqlalchemy import text

from app.services.common.permission_users import user_ids_matching, user_ids_with_permission


async def test_merge_additions_hit(db):
    # warehouse_Keeper 的 materials.subcontract_orders 仅存在于 ROLE_PERMISSION_ADDITIONS
    await db.execute(text("""
        INSERT INTO sys_role (role_code, role_name, permissions)
        VALUES ('warehouse_Keeper', 'warehouse_Keeper', CAST('{"dashboard": ["read"]}' AS jsonb))
        ON CONFLICT (role_code) DO NOTHING
    """))
    role_id = (
        await db.execute(text("SELECT id FROM sys_role WHERE role_code='warehouse_Keeper'"))
    ).scalar_one()
    await db.execute(text("""
        INSERT INTO sys_user
            (username, hashed_password, is_active, role_id, login_version,
             is_default_password, channel_sessions, font_size_scale, created_at)
        VALUES ('pytest_wh_keeper', 'x', TRUE, :role_id, 1,
                TRUE, '{}'::jsonb, '1.0', NOW())
        ON CONFLICT (username) DO NOTHING
    """), {"role_id": role_id})
    user_id = int(
        (await db.execute(text(
            "SELECT id FROM sys_user WHERE username='pytest_wh_keeper'"
        ))).scalar_one()
    )
    admin_id = int(
        (await db.execute(text("SELECT id FROM sys_user WHERE username='admin'"))).scalar_one()
    )
    ids = await user_ids_with_permission(
        db, "materials.subcontract_orders", "read", include_admin=False
    )
    assert user_id in ids
    assert admin_id not in ids


async def test_unknown_resource_returns_empty(db):
    assert await user_ids_with_permission(db, "not.exists", "read", include_admin=False) == []


async def test_admin_bypass(db):
    ids = await user_ids_with_permission(db, "not.exists", "read", include_admin=True)
    admin_id = int(
        (await db.execute(text("SELECT id FROM sys_user WHERE username='admin'"))).scalar_one()
    )
    assert ids == [admin_id]


async def test_parent_fallback_for_non_admin(db):
    await db.execute(text("""
        INSERT INTO sys_role (role_code, role_name, permissions)
        VALUES ('pytest_orders_parent', 'pytest_orders_parent',
                CAST('{"orders": ["read"]}' AS jsonb))
        ON CONFLICT (role_code) DO NOTHING
    """))
    role_id = (
        await db.execute(text(
            "SELECT id FROM sys_role WHERE role_code='pytest_orders_parent'"
        ))
    ).scalar_one()
    await db.execute(text("""
        INSERT INTO sys_user
            (username, hashed_password, is_active, role_id, login_version,
             is_default_password, channel_sessions, font_size_scale, created_at)
        VALUES ('pytest_orders_parent_user', 'x', TRUE, :role_id, 1,
                TRUE, '{}'::jsonb, '1.0', NOW())
        ON CONFLICT (username) DO NOTHING
    """), {"role_id": role_id})
    user_id = int(
        (await db.execute(text(
            "SELECT id FROM sys_user WHERE username='pytest_orders_parent_user'"
        ))).scalar_one()
    )
    ids = await user_ids_with_permission(db, "orders.list", "read", include_admin=False)
    assert user_id in ids


async def test_user_ids_matching_predicate(db):
    admin_id = (await db.execute(text("SELECT id FROM sys_user WHERE username='admin'"))).scalar_one()
    ids = await user_ids_matching(db, lambda role_code, perms: role_code == "admin")
    assert ids == [int(admin_id)]
