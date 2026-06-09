"""卡片构建器 - 统一的卡片构建逻辑"""

from typing import Any, Dict, List

from app.schemas.assistant.schemas import AssistantCard


# 工具名称到卡片标题的映射
TOOL_TYPE_LABELS = {
    "search_orders": "订单搜索结果",
    "search_purchase_orders": "采购订单搜索结果",
    "search_materials": "物料搜索结果",
    "search_production": "生产进度搜索结果",
    "search_exceptions": "异常搜索结果",
    "search_basicdata": "基础数据搜索结果",
    "search_run_orders": "跑单管理搜索结果",
    "search_invoices": "采购开票搜索结果",
    "search_eta_updates": "交期变更记录",
    "search_users": "用户搜索结果",
    "suggest_actions": "行动建议",
}


def build_summary_card(summary: Dict[str, Any], label: str = "概览") -> AssistantCard:
    """构建概览卡片"""
    return AssistantCard(
        type="summary",
        title=f"{label}交付概况",
        payload={
            "items": [
                {"label": "应交总数", "value": summary.get("due_total", 0), "color": "#1890ff"},
                {"label": "高风险", "value": summary.get("red_count", 0), "color": "#f5222d"},
                {"label": "中风险", "value": summary.get("yellow_count", 0), "color": "#faad14"},
                {"label": "逾期", "value": summary.get("overdue_count", 0), "color": "#ff4d4f"},
                {"label": "欠料", "value": summary.get("shortage_count", 0), "color": "#fa8c16"},
            ],
        },
    )


def build_search_result_card(tool_name: str, items: List[Dict[str, Any]], total: int) -> AssistantCard:
    """构建搜索结果卡片"""
    title = TOOL_TYPE_LABELS.get(tool_name, "搜索结果")
    return AssistantCard(
        type="search_result_list",
        title=f"{title}（共{total}条）",
        payload={"items": items, "total": total},
    )


def build_cards_from_tool_results(tool_results: List[Dict[str, Any]]) -> List[AssistantCard]:
    """从工具结果构建卡片列表"""
    cards: List[AssistantCard] = []

    for tr in tool_results:
        tool_name = tr["tool"]
        data = tr["data"]

        # 处理 dashboard_summary 工具
        if tool_name == "get_dashboard_summary":
            summary = data.get("summary", {})
            if summary:
                cards.append(build_summary_card(summary, data.get("label", "概览")))
            if data.get("items"):
                cards.append(AssistantCard(
                    type="search_result_list",
                    title=f"应交订单（前{len(data['items'])}条）",
                    payload={"items": data["items"], "total": data.get("total", 0)},
                ))

        # 处理 suggest_actions 工具
        elif tool_name == "suggest_actions":
            actions = data.get("actions", [])
            if actions:
                cards.append(AssistantCard(
                    type="action_list",
                    title=f"行动建议（{data.get('total', len(actions))}项）",
                    payload={
                        "actions": actions,
                        "context": data.get("context", ""),
                        "date": data.get("date", ""),
                    },
                ))

        # 处理搜索类工具
        elif tool_name in TOOL_TYPE_LABELS:
            items = data.get("items", [])
            total = data.get("total", 0)
            if items:
                cards.append(build_search_result_card(tool_name, items, total))

    return cards
