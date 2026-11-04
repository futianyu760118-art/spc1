from fastapi import APIRouter

from app.api.v1.engineering.labor_prices import router as labor_prices_router

router = APIRouter()
router.include_router(labor_prices_router, tags=["工程管理-工价"])
