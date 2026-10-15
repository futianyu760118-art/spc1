"""执行面智能体配置拉取对外接口（endpoint_code: agent.config）

agent 启动/自重启时经 HMAC 拉取 DB 配置（scope=execution_agent），空值不下发（agent 继续用 env）。
签名串 = timestamp + app_key + endpoint_code + query_string（GET 无查询参数时 query_string 为空串）。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.basicdata.data_supply import DataSupplyApiKey
from app.schemas.common import ResponseModel
from app.services.ai_config import get_agent_external_config

from ..deps import external_auth
from ..log_wrap import log_external_call
from ..registry import register_external

router = APIRouter(prefix="/agent", tags=["智能体管理"])


@router.get("/config", response_model=ResponseModel[dict],
            summary="执行面智能体配置", description="endpoint_code: agent.config")
@register_external(
    "agent.config", "执行面智能体配置", method="GET", path="/agent/config",
    description="agent 启动/自重启时拉取运行时配置（非空 DB 值覆盖 env），附配置版本号",
    tags=["智能体管理"],
)
@log_external_call("agent.config")
async def agent_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("agent.config")),
):
    return await get_agent_external_config(db)
