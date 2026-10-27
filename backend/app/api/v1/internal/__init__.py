from fastapi import APIRouter

from app.api.v1.internal import gateway

router = APIRouter()
router.include_router(gateway.router, prefix="/gateway", tags=["内网-网关"])
