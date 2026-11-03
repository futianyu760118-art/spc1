"""M01 人员离职/复职事件在 SPC 的本地适配器。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_db
from app.models.basicdata.audit_log import AuditLog
from app.models.basicdata.employee import Employee
from app.models.basicdata.user import SysUser
from app.models.common.approval_center import ApprovalInstance, ApprovalTask
from app.models.exception.quality_issue import QualityIssue
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.sale_order import SaleOrder
from app.models.production.schedule_plan import ProductionSchedulePlan
from app.models.quality.supplier_claim import SupplierClaim


router = APIRouter()

EVENT_LOG_TABLE = "person_lifecycle_event"
QUEUE_LABEL = "待重新分配"
SUPPORTED_EVENTS = {"person.offboarded", "person.reinstated"}
TERMINAL_STATUSES = {
    "archived",
    "cancelled",
    "closed",
    "completed",
    "done",
    "rejected",
}
REQUIRED_FIELDS = (
    "event_id",
    "event_type",
    "event_version",
    "tenant_id",
    "source_system",
    "object_type",
    "object_id",
    "revision",
    "idempotency_key",
    "person",
)

ASSIGNMENT_SPECS = (
    (SaleOrder, "delivery", ("owner",), None),
    (ProductionSchedulePlan, "planning", ("owner",), None),
    (PurchaseOrder, "material", ("owner",), "owner_id"),
    (
        QualityIssue,
        "quality",
        (
            "responsible_person",
            "submitter",
            "preliminary_analysis_person",
            "root_cause_analysis_person",
            "auditor",
            "missed_inspector",
        ),
        None,
    ),
    (SupplierClaim, "quality", ("applicant", "approved_by"), None),
    (ApprovalTask, "quality", ("approver",), None),
    (ApprovalInstance, "quality", ("applicant",), None),
)


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "failed", "error": message},
    )


def _lifecycle_secret_candidates(key_id: str) -> list[str]:
    current_key_id = os.getenv("AEOS_PERSON_LIFECYCLE_KEY_ID", "m01-kernel")
    previous_key_id = os.getenv("AEOS_PERSON_LIFECYCLE_PREVIOUS_KEY_ID", "")
    if key_id == current_key_id:
        names = ("AEOS_PERSON_LIFECYCLE_SECRET", "SPC_PERSON_LIFECYCLE_SECRET")
    elif previous_key_id and key_id == previous_key_id:
        names = (
            "AEOS_PERSON_LIFECYCLE_PREVIOUS_SECRET",
            "SPC_PERSON_LIFECYCLE_PREVIOUS_SECRET",
        )
    else:
        return []
    return [value for name in names if (value := os.getenv(name))]


def _canonical_messages(request: Request, timestamp: str, raw_body: bytes) -> list[bytes]:
    canonical = b"\n".join(
        (
            request.method.upper().encode("ascii"),
            request.url.path.encode("utf-8"),
            timestamp.encode("ascii"),
            raw_body,
        )
    )
    # The second form keeps the migration window compatible with the existing
    # M07/M10 adapters while new callers use the method/path-bound form above.
    legacy = timestamp.encode("ascii") + b"." + raw_body
    return [canonical, legacy]


def _verify_hmac(request: Request, raw_body: bytes) -> JSONResponse | None:
    key_id = request.headers.get("X-AEOS-Key-Id", "")
    timestamp = request.headers.get("X-AEOS-Timestamp", "")
    supplied = request.headers.get("X-AEOS-Signature", "").removeprefix("sha256=")
    if not key_id or not timestamp or not supplied:
        return _error(401, "人员同步签名无效")
    try:
        timestamp_ms = int(timestamp)
    except ValueError:
        return _error(401, "人员同步时间不正确")
    try:
        max_skew_ms = int(os.getenv("AEOS_PERSON_LIFECYCLE_MAX_SKEW_SECONDS", "300")) * 1000
    except ValueError:
        max_skew_ms = 300_000
    if abs(int(time.time() * 1000) - timestamp_ms) > max_skew_ms:
        return _error(401, "人员同步请求已过期")

    messages = _canonical_messages(request, timestamp, raw_body)
    for secret in _lifecycle_secret_candidates(key_id):
        if any(
            hmac.compare_digest(
                hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest(),
                supplied,
            )
            for message in messages
        ):
            return None
    return _error(401, "人员同步签名无效")


def _parse_event(raw_body: bytes) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, _error(400, "人员同步事件不是有效 JSON")
    if not isinstance(payload, dict):
        return None, _error(400, "人员同步事件格式不正确")
    missing = [field for field in REQUIRED_FIELDS if payload.get(field) in (None, "")]
    if missing:
        return None, _error(400, f"人员同步事件缺少必填内容：{','.join(missing)}")
    if payload.get("event_type") not in SUPPORTED_EVENTS:
        return None, _error(400, f"不支持的人员状态事件：{payload['event_type']}")
    if payload.get("event_version") != 1:
        return None, _error(400, "不支持的人员事件版本")
    if payload.get("source_system") != "M01_KERNEL" or payload.get("object_type") != "Person":
        return None, _error(400, "人员同步事件来源不受信任")
    if not isinstance(payload.get("person"), dict):
        return None, _error(400, "人员身份内容不正确")
    try:
        revision = int(payload["revision"])
    except (TypeError, ValueError):
        return None, _error(400, "人员事件 revision 不正确")
    if revision <= 0:
        return None, _error(400, "人员事件 revision 不正确")
    payload["revision"] = revision
    return payload, None


def _event_key(payload: dict[str, Any]) -> str:
    return str(payload["idempotency_key"])


async def _find_duplicate(db: AsyncSession, event_key: str) -> dict[str, Any] | None:
    row = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.table_name == EVENT_LOG_TABLE,
                AuditLog.action == "receive",
                AuditLog.new_value == event_key,
            )
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row or not row.old_value:
        return None
    try:
        result = json.loads(row.old_value)
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


async def _latest_revision(db: AsyncSession, object_id: str) -> int | None:
    return (
        await db.execute(
            select(AuditLog.record_id)
            .where(
                AuditLog.table_name == EVENT_LOG_TABLE,
                AuditLog.action == "receive",
                AuditLog.operator == object_id,
            )
            .order_by(AuditLog.record_id.desc(), AuditLog.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _record_event(
    db: AsyncSession, payload: dict[str, Any], result: dict[str, Any]
) -> None:
    db.add(
        AuditLog(
            table_name=EVENT_LOG_TABLE,
            record_id=payload["revision"],
            action="receive",
            field_name=payload["event_type"],
            old_value=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            new_value=_event_key(payload),
            operator=str(payload["object_id"]),
        )
    )
    await db.flush()


async def _resolve_identity(
    db: AsyncSession, payload: dict[str, Any]
) -> tuple[Employee | None, list[SysUser], str | None]:
    object_id = str(payload["object_id"]).strip()
    person = payload["person"]
    person_id = str(person.get("person_id") or object_id).strip()
    emp_code = str(person.get("emp_code") or "").strip()
    if person_id != object_id:
        return None, [], "人员身份冲突"

    employee_filters = []
    if person_id.isdigit():
        employee_filters.append(Employee.id == int(person_id))
    else:
        employee_filters.extend(
            (Employee.oa_user_id == person_id, Employee.login_id == person_id)
        )
    if emp_code:
        employee_filters.append(Employee.emp_code == emp_code)
    employees = (
        await db.execute(select(Employee).where(or_(*employee_filters)))
    ).scalars().all() if employee_filters else []
    unique_employees = {employee.id: employee for employee in employees}
    if len(unique_employees) > 1:
        return None, [], "人员身份冲突"
    employee = next(iter(unique_employees.values()), None)
    if employee and emp_code and employee.emp_code != emp_code:
        return None, [], "人员身份冲突"

    user_filters = []
    if emp_code:
        user_filters.append(SysUser.emp_code == emp_code)
        user_filters.append(SysUser.username == emp_code)
    if employee:
        user_filters.append(SysUser.scm_employee_id == employee.id)
    elif person_id.isdigit():
        user_filters.append(SysUser.id == int(person_id))
    users = (
        await db.execute(select(SysUser).where(or_(*user_filters)))
    ).scalars().all() if user_filters else []
    unique_users = {user.id: user for user in users}
    if len(unique_users) > 1 and employee is None:
        return None, [], "人员身份冲突"
    if employee is None and not unique_users:
        return None, [], None
    return employee, list(unique_users.values()), None


def _identity_values(
    payload: dict[str, Any], employee: Employee | None, users: list[SysUser]
) -> set[str]:
    person = payload["person"]
    values = {
        str(payload["object_id"]),
        str(person.get("person_id") or ""),
        str(person.get("emp_code") or ""),
    }
    if employee:
        values.update({str(employee.id), employee.emp_code or "", employee.emp_name})
    for user in users:
        values.update({str(user.id), user.username, user.emp_code or ""})
    return {value for value in values if value}


def _row_is_active(row: Any) -> bool:
    for name in ("status", "po_status", "approval_status"):
        value = getattr(row, name, None)
        if value is not None and str(value).strip().lower() in TERMINAL_STATUSES:
            return False
    if getattr(row, "is_closed", 0) in (1, True):
        return False
    if getattr(row, "is_deleted", False) is True:
        return False
    if hasattr(row, "is_active") and row.is_active is False:
        return False
    return True


async def _reassign_model(
    db: AsyncSession,
    model: Any,
    domain: str,
    fields: tuple[str, ...],
    owner_id_field: str | None,
    values: set[str],
    user_ids: set[int],
) -> list[str]:
    conditions = [getattr(model, field).in_(values) for field in fields]
    if owner_id_field and user_ids:
        conditions.append(getattr(model, owner_id_field).in_(user_ids))
    if not conditions:
        return []
    rows = (await db.execute(select(model).where(or_(*conditions)))).scalars().all()
    reassigned: list[str] = []
    for row in rows:
        if not _row_is_active(row):
            continue
        matched = False
        for field in fields:
            value = getattr(row, field, None)
            if value is not None and str(value) in values:
                setattr(row, field, QUEUE_LABEL)
                matched = True
        if owner_id_field and getattr(row, owner_id_field, None) in user_ids:
            setattr(row, owner_id_field, None)
            matched = True
        if matched:
            reassigned.append(f"{domain}:{model.__tablename__}:{row.id}")
    return reassigned


async def _reassign_open_work(
    db: AsyncSession, payload: dict[str, Any], employee: Employee | None, users: list[SysUser]
) -> tuple[list[str], list[str]]:
    values = _identity_values(payload, employee, users)
    user_ids = {int(user.id) for user in users}
    reassigned: list[str] = []
    domains: set[str] = set()
    for model, domain, fields, owner_id_field in ASSIGNMENT_SPECS:
        rows = await _reassign_model(
            db, model, domain, fields, owner_id_field, values, user_ids
        )
        if rows:
            domains.add(domain)
            reassigned.extend(rows)
    ordered_domains = [domain for domain in ("delivery", "planning", "material", "quality") if domain in domains]
    return ordered_domains, reassigned


def _invalidate_login(user: SysUser, active: bool) -> None:
    user.is_active = active
    user.login_version = int(user.login_version or 0) + 1
    user.channel_sessions = {}


async def _apply_offboard(
    db: AsyncSession, payload: dict[str, Any], employee: Employee | None, users: list[SysUser]
) -> dict[str, Any]:
    if employee:
        employee.status = 5
    for user in users:
        _invalidate_login(user, False)
    closed_items, reassigned_tasks = await _reassign_open_work(db, payload, employee, users)
    return {
        "status": "synced",
        "state": "offboarded",
        "event_id": payload["event_id"],
        "closed_items": closed_items,
        "reassigned_tasks": reassigned_tasks,
        "pending_confirmation": {"permissions": False, "agents": False},
        "duplicate": False,
    }


async def _apply_reinstate(
    payload: dict[str, Any], employee: Employee | None, users: list[SysUser]
) -> dict[str, Any]:
    if employee:
        employee.status = 1
    for user in users:
        _invalidate_login(user, True)
    return {
        "status": "pending_confirmation",
        "state": "active",
        "event_id": payload["event_id"],
        "closed_items": [],
        "reassigned_tasks": [],
        "pending_confirmation": {"permissions": True, "agents": True},
        "duplicate": False,
    }


def _is_future_effective(payload: dict[str, Any]) -> bool:
    effective_at = payload.get("effective_at")
    if not effective_at:
        return False
    try:
        effective = datetime.fromisoformat(str(effective_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=timezone.utc)
    return effective > datetime.now(timezone.utc)


@router.post("/aeos/person-lifecycle")
async def person_lifecycle(request: Request, db: AsyncSession = Depends(get_write_db)):
    raw_body = await request.body()
    auth_error = _verify_hmac(request, raw_body)
    if auth_error:
        return auth_error
    payload, parse_error = _parse_event(raw_body)
    if parse_error:
        return parse_error
    assert payload is not None

    duplicate = await _find_duplicate(db, _event_key(payload))
    if duplicate is not None:
        duplicate["duplicate"] = True
        return duplicate

    employee, users, identity_error = await _resolve_identity(db, payload)
    if identity_error:
        return _error(409, identity_error)
    if employee is None and not users:
        result = {
            "status": "skipped",
            "state": "unknown",
            "event_id": payload["event_id"],
            "closed_items": [],
            "reassigned_tasks": [],
            "pending_confirmation": {"permissions": False, "agents": False},
            "duplicate": False,
        }
        await _record_event(db, payload, result)
        return result

    latest_revision = await _latest_revision(db, str(payload["object_id"]))
    if latest_revision is not None and payload["revision"] <= int(latest_revision):
        result = {
            "status": "stale",
            "state": "stale",
            "event_id": payload["event_id"],
            "closed_items": [],
            "reassigned_tasks": [],
            "pending_confirmation": {"permissions": False, "agents": False},
            "duplicate": False,
        }
        await _record_event(db, payload, result)
        return result

    if _is_future_effective(payload):
        result = {
            "status": "scheduled",
            "state": "scheduled",
            "event_id": payload["event_id"],
            "closed_items": [],
            "reassigned_tasks": [],
            "pending_confirmation": {"permissions": False, "agents": False},
            "duplicate": False,
        }
    elif payload["event_type"] == "person.offboarded":
        result = await _apply_offboard(db, payload, employee, users)
    else:
        result = await _apply_reinstate(payload, employee, users)
    await _record_event(db, payload, result)
    return result
