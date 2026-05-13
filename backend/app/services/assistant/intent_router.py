"""Intent 路由器 — 按 intent 分发到对应 handler"""

import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.assistant.schemas import AssistantReply
from app.services.assistant.intent_parser import IntentResult

logger = logging.getLogger(__name__)

# handler 注册表: intent -> async handler(db, params) -> AssistantReply
_HANDLER_REGISTRY: Dict[str, Callable] = {}


def register_handler(intent: str):
    """装饰器：注册 intent handler"""
    def decorator(func):
        _HANDLER_REGISTRY[intent] = func
        return func
    return decorator


async def dispatch(intent_result: IntentResult, db: AsyncSession) -> AssistantReply:
    """根据解析结果分发到对应 handler"""
    intent = intent_result.intent
    params = intent_result.params

    handler = _HANDLER_REGISTRY.get(intent)
    if handler:
        try:
            return await handler(db, params)
        except Exception as e:
            logger.error(f"Handler [{intent}] 执行失败: {e}", exc_info=True)
            return AssistantReply(
                intent=intent,
                text=f"执行过程中出现错误: {str(e)}",
                suggestions=["重试"],
            )

    # 未匹配
    return AssistantReply(
        intent="unknown",
        text="抱歉，我暂时不理解这个问题。您可以试试以下指令：",
        suggestions=["今日交付盘点", "逾期订单", "高风险订单"],
    )


# 导入 handlers 以触发注册
from app.services.assistant.handlers import today_delivery  # noqa: E402, F401
