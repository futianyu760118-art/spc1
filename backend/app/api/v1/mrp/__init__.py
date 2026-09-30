"""MRP 域路由汇总。"""

from app.api.v1.mrp.comparison import comparison_router
from app.api.v1.mrp.exceptions import exceptions_router
from app.api.v1.mrp.order_coverage import order_coverage_router
from app.api.v1.mrp.overview import overview_router
from app.api.v1.mrp.parameters import parameters_router
from app.api.v1.mrp.runs import runs_router
from app.api.v1.mrp.substitutes import substitutes_router
from app.api.v1.mrp.suggestions import suggestions_router

__all__ = ["comparison_router", "exceptions_router", "order_coverage_router", "overview_router", "parameters_router", "runs_router", "substitutes_router", "suggestions_router"]
