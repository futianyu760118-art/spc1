"""Hub 审批后的订单受控写操作（备注/状态）与幂等控制。"""

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.models.order.sale_order import SaleOrder
from app.models.order.write_idempotency import OrderWriteIdempotency

OPERATIONS = {"order.update_note", "order.update_status", "order.update_delivery_date"}
STATUS_VALUES = {"open", "closed"}
REMARK_MAX_LENGTH = 2000
IDEMPOTENCY_KEY_MAX_LENGTH = 128
IDEMPOTENCY_RETENTION_DAYS = 30
ORDER_NO_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BUSINESS_TZ = ZoneInfo("Asia/Shanghai")


class OrderWriteError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_order_no(order_no: str) -> str:
    normalized = (order_no or "").strip()
    if not ORDER_NO_RE.match(normalized):
        raise OrderWriteError(400, "orderNo 格式无效：仅允许字母、数字、点、下划线、中划线，且不超过 64 字符")
    return normalized


def _normalize_idempotency_key(value: Optional[str], request_id: Optional[str]) -> str:
    key = (value or request_id or "").strip()
    if not key:
        raise OrderWriteError(400, "缺少 idempotencyKey（或 request_id）")
    if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise OrderWriteError(400, f"idempotencyKey 不能超过 {IDEMPOTENCY_KEY_MAX_LENGTH} 字符")
    return key


def _validate_changes(operation: str, changes: Any) -> dict:
    if not isinstance(changes, dict):
        raise OrderWriteError(400, "changes 必须是对象")
    keys = set(changes)
    if operation == "order.update_note":
        if keys != {"remark"}:
            raise OrderWriteError(400, "order.update_note 只允许 changes.remark")
        remark = changes.get("remark")
        if remark is not None and not isinstance(remark, str):
            raise OrderWriteError(400, "changes.remark 必须是字符串或 null")
        if isinstance(remark, str) and len(remark) > REMARK_MAX_LENGTH:
            raise OrderWriteError(400, f"changes.remark 不能超过 {REMARK_MAX_LENGTH} 字符")
        if isinstance(remark, str):
            return {"remark": remark.strip() or None}
        return {"remark": None}
    if operation == "order.update_status":
        if keys != {"status"}:
            raise OrderWriteError(400, "order.update_status 只允许 changes.status")
        status = changes.get("status")
        if status not in STATUS_VALUES:
            raise OrderWriteError(400, "changes.status 必须是 open 或 closed")
        return {"status": status}
    if operation == "order.update_delivery_date":
        if keys != {"deliveryDate"}:
            raise OrderWriteError(400, "order.update_delivery_date 只允许 changes.deliveryDate")
        value = changes.get("deliveryDate")
        if not isinstance(value, str) or not DATE_RE.match(value):
            raise OrderWriteError(400, "changes.deliveryDate 必须是 YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise OrderWriteError(400, "changes.deliveryDate 不是有效日期")
        return {"deliveryDate": parsed.isoformat()}
    raise OrderWriteError(400, f"CAPABILITY_UNSUPPORTED: 不支持的操作 {operation}")


def _request_hash(operation: str, order_no: str, changes: dict) -> str:
    payload = json.dumps(
        {"operation": operation, "orderNo": order_no, "changes": changes},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _replay(record: OrderWriteIdempotency) -> dict:
    result = dict(record.result_json or {})
    result["idempotent_replay"] = True
    return result


async def _find_existing(db: AsyncSession, key: str) -> Optional[OrderWriteIdempotency]:
    return (
        await db.execute(
            select(OrderWriteIdempotency).where(OrderWriteIdempotency.idempotency_key == key)
        )
    ).scalar_one_or_none()


async def _cleanup_expired(db: AsyncSession) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=IDEMPOTENCY_RETENTION_DAYS)
    await db.execute(
        delete(OrderWriteIdempotency).where(OrderWriteIdempotency.created_at < cutoff)
    )


def _before_after(order: SaleOrder, operation: str, normalized_changes: dict):
    if operation == "order.update_note":
        before = {"remark": order.remark or ""}
        after = {"remark": normalized_changes["remark"] or ""}
        return before, after
    if operation == "order.update_delivery_date":
        before = {
            "deliveryDate": order.promised_date.isoformat() if order.promised_date else None,
        }
        after = {"deliveryDate": normalized_changes["deliveryDate"]}
        return before, after
    before_status = "closed" if (order.is_closed == 1 or order.status == "closed") else "open"
    before = {"status": before_status, "is_closed": int(order.is_closed or 0)}
    after = {
        "status": normalized_changes["status"],
        "is_closed": 1 if normalized_changes["status"] == "closed" else 0,
    }
    return before, after


def _update_values(order: SaleOrder, operation: str, normalized_changes: dict) -> dict:
    if operation == "order.update_note":
        return {"remark": normalized_changes["remark"]}
    if operation == "order.update_delivery_date":
        if order.erp_status == 3:
            raise OrderWriteError(400, "订单已由 ERP 关闭，禁止修改交付日期")
        return {"promised_date": date.fromisoformat(normalized_changes["deliveryDate"])}
    if order.erp_status == 3:
        raise OrderWriteError(400, "订单已由 ERP 关闭，禁止修改状态")
    return {
        "status": normalized_changes["status"],
        "is_closed": 1 if normalized_changes["status"] == "closed" else 0,
    }


async def execute_order_write(
    db: AsyncSession,
    *,
    order_no: str,
    operation: str,
    changes: Any,
    idempotency_key: Optional[str],
    request_id: Optional[str],
    operator: str,
) -> dict:
    if operation not in OPERATIONS:
        raise OrderWriteError(400, f"CAPABILITY_UNSUPPORTED: 不支持的操作 {operation}")
    normalized_order_no = _normalize_order_no(order_no)
    normalized_changes = _validate_changes(operation, changes)
    key = _normalize_idempotency_key(idempotency_key, request_id)
    request_hash = _request_hash(operation, normalized_order_no, normalized_changes)

    await _cleanup_expired(db)

    existing = await _find_existing(db, key)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise OrderWriteError(409, "IDEMPOTENCY_CONFLICT: 同一幂等键的内容与首次请求不一致")
        if existing.result_json is None:
            raise OrderWriteError(409, "AGENT_BUSY: 同一幂等键正在处理中，请稍后重试")
        return _replay(existing)

    rows = (
        await db.execute(
            select(SaleOrder)
            .where(SaleOrder.order_no == normalized_order_no)
            .order_by(SaleOrder.id.asc())
        )
    ).scalars().all()
    if not rows:
        raise OrderWriteError(404, "订单不存在")
    order = rows[-1]
    if order.is_deleted == 1:
        raise OrderWriteError(400, "订单已删除，禁止写入")

    before, after = _before_after(order, operation, normalized_changes)
    update_values = _update_values(order, operation, normalized_changes)

    record = OrderWriteIdempotency(
        idempotency_key=key,
        request_hash=request_hash,
        operation=operation,
        order_no=normalized_order_no,
        result_json=None,
    )
    db.add(record)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = await _find_existing(db, key)
        if existing is not None and existing.request_hash == request_hash:
            if existing.result_json is None:
                raise OrderWriteError(409, "AGENT_BUSY: 同一幂等键正在处理中，请稍后重试")
            return _replay(existing)
        raise OrderWriteError(409, "IDEMPOTENCY_CONFLICT: 同一幂等键的内容与首次请求不一致")

    await log_audit(
        db,
        "sale_order",
        order.id,
        "update",
        old_obj=order,
        update_data=update_values,
        operator=operator,
    )
    for row in rows:
        for field, value in update_values.items():
            setattr(row, field, value)
    await db.flush()
    await db.refresh(order)

    applied_at = datetime.now(_BUSINESS_TZ).isoformat(timespec="seconds")
    result = {
        "ok": True,
        "operation": operation,
        "target": {"orderNo": normalized_order_no},
        "before": before,
        "after": after,
        "appliedAt": applied_at,
        "idempotent_replay": False,
    }
    record.result_json = result
    await db.flush()
    return result
