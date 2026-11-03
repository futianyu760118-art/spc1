from fastapi import APIRouter

from app.api.v1.internal import gateway, person_lifecycle

router = APIRouter()
router.include_router(gateway.router, prefix="/gateway", tags=["内网-网关"])
router.include_router(person_lifecycle.router, prefix="/aeos", tags=["内网-AEOS人员生命周期"])
