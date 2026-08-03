from fastapi import APIRouter
from app.api.v1.writeback.enqueue import router as enqueue_router
from app.api.v1.writeback.queue import router as queue_router
from app.api.v1.writeback.log import router as log_router
from app.api.v1.writeback.stats import router as stats_router
from app.api.v1.writeback.config import router as config_router

router = APIRouter(prefix="/writeback", tags=["writeback"])
router.include_router(enqueue_router)
router.include_router(queue_router)
router.include_router(log_router)
router.include_router(stats_router)
router.include_router(config_router)
