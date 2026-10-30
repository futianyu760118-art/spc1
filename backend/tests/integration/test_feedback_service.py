"""问题反馈服务：创建落库+处理人通知；撤销三态（本人 pending / 非本人 / 非 pending）。"""

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.basicdata.announcement import Notification
from app.models.basicdata.feedback import Feedback
from app.services.basicdata.feedback_service import (
    FeedbackRevokeError,
    create_feedback,
    revoke_feedback,
)
from tests.conftest import get_user_id_by_username


async def test_create_feedback_notifies_handlers(_test_db):
    submitter_id = await get_user_id_by_username("qa_fin")
    async with AsyncSessionLocal() as db:
        fb, handler_ids = await create_feedback(
            db, submitter_id=submitter_id, submitter_name="qa_fin",
            title="页面报错", description="点击保存报 500", subtype="issue", severity="high",
        )
        assert fb.id and fb.status == "pending"
        assert handler_ids, "至少应通知 admin 处理人"
        notes = (await db.execute(
            select(Notification).where(
                Notification.ref_type == "feedback", Notification.ref_id == fb.id,
            )
        )).scalars().all()
        assert notes and all(n.type == "feedback" for n in notes)
        assert any(n.priority == "important" for n in notes)
        await db.rollback()


async def test_revoke_feedback_only_own_pending(_test_db):
    submitter_id = await get_user_id_by_username("qa_fin")
    other_id = await get_user_id_by_username("qa_mgr")

    async with AsyncSessionLocal() as db:
        fb, _ = await create_feedback(
            db, submitter_id=submitter_id, submitter_name="qa_fin",
            title="待撤销", description="d",
        )
        with pytest.raises(FeedbackRevokeError):
            await revoke_feedback(db, feedback_id=fb.id, user_id=other_id)
        fb.status = "processing"
        await db.flush()
        with pytest.raises(FeedbackRevokeError):
            await revoke_feedback(db, feedback_id=fb.id, user_id=submitter_id)
        await db.rollback()

    async with AsyncSessionLocal() as db:
        fb2, _ = await create_feedback(
            db, submitter_id=submitter_id, submitter_name="qa_fin",
            title="撤销成功", description="d",
        )
        result = await revoke_feedback(db, feedback_id=fb2.id, user_id=submitter_id)
        assert result["deleted"] == fb2.id
        gone = (await db.execute(
            select(Feedback).where(Feedback.id == fb2.id)
        )).scalar_one_or_none()
        assert gone is None
        await db.rollback()
