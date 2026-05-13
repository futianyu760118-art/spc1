"""Intent 解析器 — 优先尝试 LLM structured_output，退化到关键词正则"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel

from app.services.ai import ai_service, NotSupportedError

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    intent: str = "unknown"
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


# ---------- LLM Schema ----------

class IntentSchema(BaseModel):
    intent: str
    params: Dict[str, Any] = {}


# ---------- 关键词规则表 ----------

KEYWORD_RULES = [
    {
        "intent": "today_delivery",
        "keywords": [r"今日交付", r"今天应交", r"今日盘点", r"今日订单", r"今天交付", r"今天订单"],
    },
    {
        "intent": "overdue_orders",
        "keywords": [r"逾期订单", r"超期订单", r"延期订单", r"过期订单"],
    },
    {
        "intent": "risk_orders",
        "keywords": [r"高风险订单", r"风险订单", r"红灯订单"],
    },
    {
        "intent": "weekly_outlook",
        "keywords": [r"本周交付", r"本周展望", r"这周订单", r"未来7天"],
    },
]


def _rule_based_parse(message: str) -> IntentResult:
    """关键词正则匹配"""
    text = message.strip().lower()
    for rule in KEYWORD_RULES:
        for kw in rule["keywords"]:
            if re.search(kw, text):
                return IntentResult(intent=rule["intent"], confidence=0.8)
    return IntentResult(intent="unknown", confidence=0.0)


async def parse_intent(message: str) -> IntentResult:
    """解析用户意图：先尝试 LLM，失败走关键词"""
    # 尝试 LLM 结构化输出
    try:
        prompt = (
            f"用户输入: \"{message}\"\n"
            "请识别用户意图。可选 intent 值: today_delivery, overdue_orders, risk_orders, weekly_outlook, unknown\n"
            "如果用户提到具体客户或型号，提取到 params 中(customer/product)。"
        )
        result = await ai_service.structured_output(prompt, IntentSchema)
        logger.info(f"[LLM intent] intent={result.intent}, params={result.params}")
        return IntentResult(intent=result.intent, params=result.params, confidence=0.95)
    except (NotSupportedError, Exception) as e:
        logger.debug(f"LLM intent 解析不可用({type(e).__name__}), 使用规则解析")

    # 退化到规则
    return _rule_based_parse(message)
