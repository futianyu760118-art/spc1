"""MRP 域路由汇总。"""

from app.api.v1.mrp.comparison import comparison_router
from app.api.v1.mrp.exceptions import exceptions_router
from app.api.v1.mrp.parameters import parameters_router
from app.api.v1.mrp.runs import runs_router
from app.api.v1.mrp.suggestions import suggestions_router

__all__ = ["comparison_router", "exceptions_router", "parameters_router", "runs_router", "suggestions_router"]
