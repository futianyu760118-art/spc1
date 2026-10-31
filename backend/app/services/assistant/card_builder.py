"""卡片构建器 — 按查询路径（query-agent 白名单 path）生成卡片"""

from typing import Any, Dict, List

from app.schemas.assistant.schemas import AssistantCard
from app.services.assistant.task_router import QUERY_CATALOG


def _path_name(path: str) -> str:
    return next((c["name"] for c in QUERY_CATALOG if c["path"] == path), path)


def build_cards_from_query_results(query_results: List[Dict[str, Any]]) -> List[AssistantCard]:
    """从查询智能体结果构建卡片列表；推理结果不生成卡片（由最终答复文字承载）。"""
    cards: List[AssistantCard] = []
    for qr in query_results:
        path = qr.get("path") or ""
        data = qr.get("data") or {}
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
            cards.append(AssistantCard(
                type="search_result_list",
                title=f"{_path_name(path)}（共{total}条）",
                payload={"items": items, "total": total},
            ))
    return cards
