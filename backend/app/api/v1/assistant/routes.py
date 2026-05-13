"""智能助手 API 路由"""

import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.assistant.schemas import ChatMessageIn, AssistantReply, SkillItem
from app.services.assistant.intent_parser import parse_intent, KEYWORD_RULES
from app.services.assistant.intent_router import dispatch
from app.services.ai import ai_service

router = APIRouter()


@router.post("/chat", response_model=dict)
async def chat(
    body: ChatMessageIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """接收用户消息，解析意图并返回结构化回复"""
    intent_result = await parse_intent(body.message)
    reply = await dispatch(intent_result, db)

    # 补充 session_id 和 provider 信息
    reply.session_id = body.session_id or str(uuid.uuid4())
    reply.provider = ai_service.current_provider()

    return {"code": 0, "data": reply.model_dump()}


@router.get("/skills", response_model=dict)
async def list_skills(current_user=Depends(get_current_user)):
    """返回当前支持的技能清单"""
    skills = [
        SkillItem(
            intent="today_delivery",
            name="今日交付盘点",
            description="查看今日应交付订单及风险分布",
            keywords=["今日交付", "今天应交", "今日盘点"],
        ),
        SkillItem(
            intent="overdue_orders",
            name="逾期订单",
            description="查看已逾期未交付的订单（开发中）",
            keywords=["逾期订单", "超期订单"],
        ),
        SkillItem(
            intent="risk_orders",
            name="高风险订单",
            description="查看高风险评分订单（开发中）",
            keywords=["高风险订单", "红灯订单"],
        ),
        SkillItem(
            intent="weekly_outlook",
            name="本周交付展望",
            description="未来7天应交订单预览（开发中）",
            keywords=["本周交付", "这周订单"],
        ),
    ]
    return {"code": 0, "data": [s.model_dump() for s in skills]}
