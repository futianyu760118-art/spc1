"""完整性规则 TTL 缓存 + 确定性校验（不依赖 DB session）。"""

import logging
import time
from typing import Dict, List, Tuple

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.common.completeness_rule import CompletenessRule
from app.services.notification.assistant_notify import BIZ_NOTIFY_CONFIG

logger = logging.getLogger(__name__)

RULE_TTL_S = 60.0
_cache: Dict[str, object] = {"ts": 0.0, "rules": {}, "loaded": False}
_disabled_logged = False


async def refresh_rules(force: bool = False) -> None:
    global _disabled_logged
    now = time.monotonic()
    if not force and now - float(_cache["ts"]) < RULE_TTL_S:
        return
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(CompletenessRule).where(
                        CompletenessRule.enabled.is_(True),
                        CompletenessRule.required.is_(True),
                    )
                )
            ).scalars().all()
    except Exception as e:
        logger.warning("completeness rules load failed: %s", e)
        _cache["ts"] = now
        if not _cache["loaded"] and not _disabled_logged:
            _disabled_logged = True
            logger.error("gap_check_disabled reason=rules_unavailable")
        return

    grouped: Dict[str, List[Tuple[str, str]]] = {}
    seen = set()
    for row in rows:
        available = (BIZ_NOTIFY_CONFIG.get(row.biz_type) or {}).get("available_fields") or []
        if row.field_key not in available:
            logger.error("rules_invalid biz_type=%s field_key=%s reason=not_available",
                         row.biz_type, row.field_key)
            continue
        key = (row.biz_type, row.field_key)
        if key in seen:
            logger.error("rules_invalid biz_type=%s field_key=%s reason=duplicate",
                         row.biz_type, row.field_key)
            continue
        seen.add(key)
        grouped.setdefault(row.biz_type, []).append((row.field_key, row.label))

    _cache["rules"] = grouped
    _cache["ts"] = now
    _cache["loaded"] = True
    if _disabled_logged:
        _disabled_logged = False
        logger.info("gap_check_enabled")
    logger.info("rules_loaded count=%s", sum(len(v) for v in grouped.values()))


def check_completeness(*, biz_type: str, biz_no: str, values: Dict[str, object]) -> List[Tuple[str, str]]:
    """返回 [(field_key, label)]；values 中不存在的字段视为 unknown，不计缺失。"""
    rules = (_cache["rules"] or {}).get(biz_type) or []
    missing: List[Tuple[str, str]] = []
    for field_key, label in rules:
        if field_key not in values:
            continue
        value = values[field_key]
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append((field_key, label))
    return sorted(missing, key=lambda item: item[0])
