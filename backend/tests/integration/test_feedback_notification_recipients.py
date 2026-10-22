"""feedback 处理人通知收件人的回归测试（覆盖 DRY 替换后的取人逻辑）。"""

from types import SimpleNamespace

from sqlalchemy import text

from app.api.v1.basicdata.feedback import _insert_handler_notifications


async def test_handler_notifications_follow_permission_and_exclude_submitter(db):
    await db.execute(text("""
        INSERT INTO sys_role (role_code, role_name, permissions)
        VALUES ('pytest_feedback_handler', 'pytest_feedback_handler',
                CAST(:perms AS jsonb))
        ON CONFLICT (role_code) DO NOTHING
    """), {"perms": '{"basicdata.feedback": ["update"]}'})
    role_id = (
        await db.execute(text(
            "SELECT id FROM sys_role WHERE role_code='pytest_feedback_handler'"
        ))
    ).scalar_one()
    await db.execute(text("""
        INSERT INTO sys_user
            (username, hashed_password, is_active, role_id, login_version,
             is_default_password, channel_sessions, font_size_scale, created_at)
        VALUES ('pytest_fb_handler', 'x', TRUE, :role_id, 1,
                TRUE, '{}'::jsonb, '1.0', NOW())
        ON CONFLICT (username) DO NOTHING
    """), {"role_id": role_id})
    handler_id = int(
        (await db.execute(text(
            "SELECT id FROM sys_user WHERE username='pytest_fb_handler'"
        ))).scalar_one()
    )
    submitter_id = int(
        (await db.execute(text("SELECT id FROM sys_user WHERE username='admin'"))).scalar_one()
    )

    feedback = SimpleNamespace(
        submitter_id=submitter_id,
        submitter_name="admin",
        severity="high",
        title="测试反馈",
        description="描述",
        id=999,
    )
    notified = await _insert_handler_notifications(db, feedback)

    assert handler_id in notified
    assert submitter_id not in notified
    rows = (
        await db.execute(text(
            "SELECT user_id, type, priority, title FROM notification WHERE ref_id=999"
        ))
    ).all()
    assert {(int(r[0]), r[1], r[2]) for r in rows} >= {(handler_id, "feedback", "important")}
    assert all(r[3].startswith("[问题反馈]") for r in rows)
