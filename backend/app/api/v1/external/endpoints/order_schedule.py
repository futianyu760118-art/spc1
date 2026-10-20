"""外部接口 — 订单计划字段写入（endpoint_code: orders.schedule.update）

执行面订单智能体专用：白名单四字段（出货计划/发货完成/客户验货/上线时间），
直接写订单头并审计（operator 含 Hub runId）。只写 sale_order，不动明细行。
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.models.basicdata.data_supply import DataSupplyApiKey
from app.models.order.sale_order import SaleOrder
from app.schemas.common import ResponseModel

from ..deps import external_auth
from ..log_wrap import log_external_call
from ..registry import register_external

router = APIRouter(prefix="/orders", tags=["订单"])

WRITABLE_FIELDS = (
    "shipping_plan",
    "delivery_completed_date",
    "customer_inspection_date",
    "planned_start_date",
)


class OrderScheduleFields(BaseModel):
    shipping_plan: Optional[date] = Field(None, description="出货计划，null=清空")
    delivery_completed_date: Optional[date] = Field(None, description="发货完成时间，null=清空")
    customer_inspection_date: Optional[date] = Field(None, description="客户验货时间，null=清空")
    planned_start_date: Optional[date] = Field(None, description="上线时间，null=清空")


class OrderScheduleIn(BaseModel):
    fields: OrderScheduleFields
    request_id: Optional[str] = None


@router.put("/{order_no}/schedule", response_model=ResponseModel[dict],
            summary="订单计划字段写入", description="endpoint_code: orders.schedule.update")
@register_external(
    "orders.schedule.update", "订单计划字段写入", method="PUT", path="/orders/{order_no}/schedule",
    description="执行面订单智能体专用：白名单四字段直接写订单头并审计",
    tags=["订单"],
)
@log_external_call("orders.schedule.update", path_params=("order_no",))
async def order_schedule_update(
    order_no: str,
    body: OrderScheduleIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("orders.schedule.update")),
):
    order = (await db.execute(
        select(SaleOrder).where(SaleOrder.order_no == order_no).order_by(SaleOrder.id.desc()).limit(1)
    )).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.erp_status == 3:
        raise HTTPException(status_code=400, detail="订单已关闭，禁止写入")
    if order.is_deleted == 1:
        raise HTTPException(status_code=400, detail="订单已删除，禁止写入")

    fields = body.fields.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="fields 至少一个字段")

    run_id = request.headers.get("X-Agent-Run-Id", "")
    operator = f"order-agent:{run_id}" if run_id else "order-agent"
    await log_audit(db, "sale_order", order.id, "update", old_obj=order, update_data=fields, operator=operator)
    for field_name, value in fields.items():
        setattr(order, field_name, value)
    await db.flush()
    await db.refresh(order)

    snapshot = {
        "order_no": order.order_no,
        "fields": {
            name: (getattr(order, name).isoformat() if getattr(order, name) else None)
            for name in WRITABLE_FIELDS
        },
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }
    return snapshot
