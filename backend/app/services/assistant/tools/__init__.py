"""Assistant Tools — 导入所有工具以触发注册"""

from app.services.assistant.tools import (  # noqa: F401
    search_orders,
    search_purchase_orders,
    search_materials,
    search_production,
    search_exceptions,
    search_basicdata,
    dashboard_summary,
    search_run_orders,
    search_invoices,
    search_eta_updates,
    search_users,
    suggest_actions,
)
