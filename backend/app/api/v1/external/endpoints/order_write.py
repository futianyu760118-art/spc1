"""外部接口 — 订单受控写操作（endpoint_code: orders.write）

仅接受 Hub 审批通过后的订单备注/状态写操作；操作白名单、状态机与幂等由
write_service 统一校验，绝不作为通用字段/SQL 写入口。
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_db
from app.models.basicdata.data_supply import DataSupplyApiKey
from app.schemas.common import ResponseModel
from app.services.order.write_service import OrderWriteError, execute_order_write

from ..common import ExternalEnvelopeError
from ..deps import external_auth
from ..log_wrap import log_external_call
from ..registry import register_external
from .order_common import resolve_operator

router = APIRouter(prefix="/orders", tags=["订单"])


class OrderWriteIn(BaseModel):
    operation: str = Field(..., description="order.update_note / order.update_status")
    changes: dict[str, Any] = Field(..., description="按 operation 只允许 remark 或 status")
    idempotencyKey: Optional[str] = Field(None, max_length=128, description="幂等键")
    request_id: Optional[str] = Field(None, max_length=128, description="调用方请求 ID")


@router.put("/{order_no}/write", response_model=ResponseModel[dict],
            summary="订单受控写操作", description="endpoint_code: orders.write")
@register_external(
    "orders.write", "订单受控写操作", method="PUT", path="/orders/{order_no}/write",
    description="Hub 审批后的订单备注/状态写操作；操作白名单、状态机、幂等键校验",
    tags=["订单"],
)
@log_external_call("orders.write", path_params=("order_no",))
async def order_write(
    order_no: str,
    body: OrderWriteIn,
    request: Request,
    db: AsyncSession = Depends(get_write_db),
    key: DataSupplyApiKey = Depends(external_auth("orders.write")),
):
    operator = await resolve_operator(db, request)
    try:
        result = await execute_order_write(
            db,
            order_no=order_no,
            operation=body.operation,
            changes=body.changes,
            idempotency_key=body.idempotencyKey,
            request_id=body.request_id,
            operator=operator,
        )
    except OrderWriteError as e:
        raise ExternalEnvelopeError(e.code, e.message)
    return result
