"""智能体会话持久化与归属校验（SQL 事实来源，Redis 热窗口）。"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent.agent import Agent
from app.models.agent.conversation import AgentConversation, AgentMessage
from app.services.agent.errors import AgentError


class ConversationError(AgentError):
    pass


async def get_owned_conversation(
    db: AsyncSession,
    conversation_id: int,
    *,
    user_id: int,
    agent_id: int,
) -> AgentConversation:
    conversation = await db.get(AgentConversation, int(conversation_id))
    if not conversation:
        raise ConversationError("会话不存在", 404)
    if int(conversation.user_id) != int(user_id) or int(conversation.agent_id) != int(agent_id):
        raise ConversationError("无权访问该会话", 403)
    return conversation


async def create_conversation(
    db: AsyncSession,
    *,
    agent: Agent,
    user_id: int,
    title: Optional[str] = None,
) -> AgentConversation:
    conversation = AgentConversation(
        agent_id=agent.id,
        user_id=int(user_id),
        task_id=None,
        title=(title or "")[:200] or None,
        status="active",
        last_message_at=datetime.now(),
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def resolve_conversation(
    db: AsyncSession,
    *,
    agent: Agent,
    user_id: int,
    conversation_id: Optional[int] = None,
) -> AgentConversation:
    if conversation_id:
        return await get_owned_conversation(
            db, conversation_id, user_id=user_id, agent_id=agent.id,
        )
    return await create_conversation(db, agent=agent, user_id=user_id)


async def append_message(
    db: AsyncSession,
    conversation: AgentConversation,
    *,
    role: str,
    content: Optional[str] = None,
    tool_calls: Optional[list] = None,
    tool_results: Optional[list] = None,
    token_usage: Optional[dict] = None,
    trace_id: Optional[str] = None,
) -> AgentMessage:
    message = AgentMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_results=tool_results,
        token_usage=token_usage,
        trace_id=trace_id,
    )
    db.add(message)
    conversation.last_message_at = datetime.now()
    if role == "user" and content and not conversation.title:
        conversation.title = content.strip().replace("\n", " ")[:50]
    await db.flush()
    return message


async def load_recent_messages(
    db: AsyncSession,
    conversation_id: int,
    *,
    limit: int = 20,
) -> List[dict]:
    rows = (await db.execute(
        select(AgentMessage)
        .where(AgentMessage.conversation_id == int(conversation_id))
        .order_by(AgentMessage.id.desc())
        .limit(limit)
    )).scalars().all()
    rows.reverse()
    return [
        {
            "role": row.role,
            "content": row.content,
            "tool_calls": row.tool_calls,
            "tool_results": row.tool_results,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
        if row.role in ("user", "assistant", "system")
    ]


async def list_conversations(
    db: AsyncSession,
    *,
    agent_id: int,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    from sqlalchemy import func

    conditions = [AgentConversation.agent_id == agent_id, AgentConversation.user_id == int(user_id)]
    total = int((await db.execute(
        select(func.count(AgentConversation.id)).where(*conditions)
    )).scalar() or 0)
    rows = (await db.execute(
        select(AgentConversation)
        .where(*conditions)
        .order_by(AgentConversation.last_message_at.desc().nullslast(), AgentConversation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "task_id": row.task_id,
                "status": row.status,
                "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def conversation_messages(db: AsyncSession, conversation: AgentConversation, limit: int = 100) -> dict:
    rows = (await db.execute(
        select(AgentMessage)
        .where(AgentMessage.conversation_id == conversation.id)
        .order_by(AgentMessage.id.asc())
        .limit(limit)
    )).scalars().all()
    return {
        "id": conversation.id,
        "title": conversation.title,
        "task_id": conversation.task_id,
        "status": conversation.status,
        "messages": [
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "tool_calls": row.tool_calls,
                "tool_results": row.tool_results,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


async def archive_conversation(db: AsyncSession, conversation: AgentConversation) -> dict:
    conversation.status = "archived"
    await db.flush()
    return {"id": conversation.id, "status": conversation.status}
