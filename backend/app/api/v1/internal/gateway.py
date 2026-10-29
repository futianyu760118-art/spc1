"""网关内网接口：只允许 gateway 容器调用。"""

import hmac
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_write_db
from app.services.agent.gateway_resolver import resolve_dispatch

router = APIRouter()


class CallerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    systemId: Optional[str] = None
    agentId: Optional[str] = None
    userId: Optional[str] = None
    taskId: Optional[str] = None
    traceId: Optional[str] = None


class ResolveCallerIn(BaseModel):
    runId: str = Field(min_length=1, max_length=128)
    traceId: Optional[str] = Field(default=None, max_length=128)
    capability: str = Field(min_length=1, max_length=64)
    input: Dict[str, Any] = Field(default_factory=dict)
    caller: Optional[CallerIn] = None


def _verify_token(x_gateway_token: Optional[str] = Header(default=None)) -> None:
    expected = get_settings().GATEWAY_INTERNAL_TOKEN
    if not expected:
        raise HTTPException(status_code=503, detail="网关内网接口未配置")
    if not x_gateway_token or not hmac.compare_digest(x_gateway_token, expected):
        raise HTTPException(status_code=401, detail="X-Gateway-Token 无效")


def _error(status_code: int, message: str, reason: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": status_code, "message": message, "data": {"reason": reason}},
    )


@router.post("/resolve-caller", dependencies=[Depends(_verify_token)])
async def resolve_caller(body: ResolveCallerIn, db: AsyncSession = Depends(get_write_db)):
    caller = body.caller.model_dump() if body.caller else None
    result = await resolve_dispatch(
        db,
        run_id=body.runId,
        trace_id=body.traceId,
        capability=body.capability,
        input_data=body.input,
        caller=caller,
    )
    if not result.ok:
        status_code = 400 if result.reject_reason == "INVALID_ARGUMENT" else 403
        return _error(status_code, f"caller 路由失败：{result.reject_reason}", result.reject_reason or "")
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "mode": result.mode,
            "userId": int(result.user.id) if result.user else None,
            "actorToken": result.actor_token,
            "expiresIn": 300 if result.actor_token else None,
        },
    }
