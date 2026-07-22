"""通用健康检查 / 对外联调用 ping 端点。"""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user_or_api_key
from app.schemas.common import ResponseModel
from app.services.basicdata.exposable_registry import exposable


router = APIRouter()


@router.get("/ping")
@exposable(
    endpoint_code="int:health.ping",
    name="健康检查（对外签名联调）",
    description="供外部系统验证 HMAC 签名机制是否正确配置",
    tags=["health"],
)
async def ping(current_user: dict = Depends(get_current_user_or_api_key)):
    """JWT 与 HMAC 均可调用。"""
    return ResponseModel(code=0, message="pong", data={"ok": True})