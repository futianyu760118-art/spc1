"""助手会话持久化：写操作确认结果落库后，历史回看与实况一致（卡片状态 + 结果消息）。"""

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.agent.conversation import AgentConversation, AgentMessage
from app.services.assistant import orchestrator


async def test_confirmation_outcome_persisted_to_history(_test_db):
    async with AsyncSessionLocal() as db:
        conv = AgentConversation(user_id=1, title="写操作", status="active")
        db.add(conv)
        await db.flush()
        original = AgentMessage(
            conversation_id=conv.id, role="assistant", content="检测到订单写操作",
            tool_calls=[{
                "tool": "call_order_agent", "agent_label": "计划写入员",
                "status": "pending_confirmation", "summary": "订单 X 写操作等待用户确认",
            }],
            tool_results={"confirmation": {
                "confirmation_id": "wc-1", "order_no": "X", "fields": [], "status": "pending",
            }},
        )
        db.add(original)
        await db.flush()

        await orchestrator._persist_confirmation_outcome(
            db, session_id=f"1:{conv.id}", confirmation_id="wc-1",
            confirmation={"confirmation_id": "wc-1", "status": "cancelled", "order_no": "X", "fields": []},
            content="已取消订单 X 的写操作，订单未做任何修改。",
        )
        await db.flush()

        rows = (await db.execute(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conv.id)
            .order_by(AgentMessage.id)
        )).scalars().all()
        assert len(rows) == 2
        assert rows[0].tool_results["confirmation"]["status"] == "cancelled"
        assert rows[0].tool_calls[0]["status"] == "cancelled"
        assert rows[1].role == "assistant"
        assert "已取消订单 X" in rows[1].content
        await db.rollback()
