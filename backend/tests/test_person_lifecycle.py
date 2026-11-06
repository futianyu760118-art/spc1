"""SPC 人员离职/复职适配器的契约测试。"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.models.basicdata.audit_log import AuditLog
from app.models.basicdata.employee import Employee
from app.models.basicdata.user import SysRole, SysUser
from app.models.exception.quality_issue import QualityIssue
from app.models.material.purchase_order import PurchaseOrder
from app.models.order.sale_order import SaleOrder
from app.models.production.schedule_plan import ProductionSchedulePlan


SECRET = "spc-person-lifecycle-test-secret"
KEY_ID = "m01-kernel"
PATH = "/api/v1/internal/aeos/person-lifecycle"


def lifecycle_event(
    *,
    person_id: str,
    emp_code: str,
    event_id: str = "evt-spc-offboard-1",
    event_type: str = "person.offboarded",
    revision: int = 1,
    status: str = "inactive",
    employment_action: str = "offboard",
) -> dict:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_version": 1,
        "tenant_id": "tenant-hengjian",
        "source_system": "M01_KERNEL",
        "object_type": "Person",
        "object_id": person_id,
        "revision": revision,
        "occurred_at": "2026-11-03T02:00:00Z",
        "effective_at": "2026-11-03T02:00:00Z",
        "correlation_id": event_id,
        "trace_id": event_id,
        "idempotency_key": (
            f"tenant-hengjian:M01_KERNEL:Person:{person_id}:{revision}:{event_type}"
        ),
        "person": {"person_id": person_id, "emp_code": emp_code},
        "status": status,
        "employment_action": employment_action,
        "occurred_by": "P_OWNER",
    }


def signed_headers(body: dict, *, secret: str = SECRET, timestamp: int | None = None) -> dict[str, str]:
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp_value = str(timestamp or int(time.time() * 1000))
    canonical = b"POST\n" + PATH.encode() + b"\n" + timestamp_value.encode() + b"\n" + raw
    signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-AEOS-Key-Id": KEY_ID,
        "X-AEOS-Timestamp": timestamp_value,
        "X-AEOS-Signature": f"sha256={signature}",
    }


async def post_event(client: AsyncClient, body: dict, *, secret: str = SECRET):
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    return await client.post(PATH, content=raw, headers=signed_headers(body, secret=secret))


async def seed_spc_person(db):
    role_id = await db.scalar(select(SysRole.id).where(SysRole.role_code == "admin"))
    employee = Employee(emp_code="E-SPC-LIFE", emp_name="SPC生命周期测试人员", status=1)
    db.add(employee)
    await db.flush()
    user = SysUser(
        username="spc-life-user",
        hashed_password="not-used",
        role_id=role_id,
        emp_code=employee.emp_code,
        scm_employee_id=employee.id,
        is_active=True,
    )
    db.add(user)
    db.add_all(
        [
            SaleOrder(order_no="SO-SPC-LIFE", line_no="10", owner=employee.emp_code),
            ProductionSchedulePlan(
                department="装配",
                plan_date=datetime(2026, 11, 3).date(),
                order_no="SO-SPC-LIFE",
                owner=employee.emp_code,
                status="planned",
            ),
            PurchaseOrder(
                po_no="PO-SPC-LIFE",
                detail_id=1,
                material_code="MAT-SPC-LIFE",
                po_status="open",
                owner=employee.emp_code,
                owner_id=user.id,
            ),
            QualityIssue(
                issue_no="QI-SPC-LIFE",
                responsible_person=employee.emp_code,
                status="open",
            ),
        ]
    )
    await db.commit()
    return employee, user


@pytest.fixture
async def lifecycle_client(db):
    from app.core.database import get_write_db

    module_path = Path(__file__).parents[1] / "app/api/v1/internal/person_lifecycle.py"
    module_spec = importlib.util.spec_from_file_location("spc_person_lifecycle", module_path)
    lifecycle_module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(lifecycle_module)

    application = FastAPI()
    application.include_router(lifecycle_module.router, prefix="/api/v1/internal")

    async def override_write_db():
        yield db

    application.dependency_overrides[get_write_db] = override_write_db
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as async_client:
        yield async_client


@pytest.fixture
async def spc_person(db):
    await db.run_sync(
        lambda sync_session: ProductionSchedulePlan.__table__.create(
            sync_session.connection(), checkfirst=True
        )
    )
    await db.execute(delete(QualityIssue).where(QualityIssue.issue_no == "QI-SPC-LIFE"))
    await db.execute(delete(PurchaseOrder).where(PurchaseOrder.po_no == "PO-SPC-LIFE"))
    await db.execute(
        delete(ProductionSchedulePlan).where(ProductionSchedulePlan.order_no == "SO-SPC-LIFE")
    )
    await db.execute(delete(SaleOrder).where(SaleOrder.order_no == "SO-SPC-LIFE"))
    await db.execute(
        delete(SysUser).where(
            SysUser.username.in_(
                ["spc-life-user", "spc-unrelated-id-collision"]
            )
        )
    )
    await db.execute(
        delete(Employee).where(Employee.emp_code.in_(["E-SPC-LIFE", "E-SPC-OTHER"]))
    )
    await db.execute(delete(AuditLog).where(AuditLog.table_name == "person_lifecycle_event"))
    await db.commit()
    employee, user = await seed_spc_person(db)
    yield employee, user
    await db.execute(delete(QualityIssue).where(QualityIssue.issue_no == "QI-SPC-LIFE"))
    await db.execute(delete(PurchaseOrder).where(PurchaseOrder.po_no == "PO-SPC-LIFE"))
    await db.execute(
        delete(ProductionSchedulePlan).where(ProductionSchedulePlan.order_no == "SO-SPC-LIFE")
    )
    await db.execute(delete(SaleOrder).where(SaleOrder.order_no == "SO-SPC-LIFE"))
    await db.execute(
        delete(SysUser).where(
            SysUser.username.in_(
                ["spc-life-user", "spc-unrelated-id-collision"]
            )
        )
    )
    await db.execute(delete(Employee).where(Employee.emp_code == "E-SPC-LIFE"))
    await db.execute(
        delete(AuditLog).where(AuditLog.table_name == "person_lifecycle_event")
    )
    await db.commit()


@pytest.mark.asyncio
async def test_offboard_closes_spc_assignments_and_queues_reassignment(
    lifecycle_client, db, spc_person, monkeypatch
):
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_SECRET", SECRET)
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_KEY_ID", KEY_ID)
    employee, user = spc_person
    body = lifecycle_event(person_id=str(employee.id), emp_code=employee.emp_code)
    unrelated_user = SysUser(
        id=employee.id,
        username="spc-unrelated-id-collision",
        hashed_password="not-used",
        role_id=user.role_id,
        is_active=True,
    )
    db.add(unrelated_user)
    await db.commit()

    response = await post_event(lifecycle_client, body)

    assert response.status_code == 200
    assert response.json()["status"] == "synced"
    assert set(response.json()["closed_items"]) == {
        "delivery",
        "planning",
        "material",
        "quality",
    }
    assert len(response.json()["reassigned_tasks"]) == 4

    await db.refresh(user)
    assert user.is_active is False
    await db.refresh(unrelated_user)
    assert unrelated_user.is_active is True
    assert (
        await db.scalar(select(SaleOrder.owner).where(SaleOrder.order_no == "SO-SPC-LIFE"))
        == "待重新分配"
    )
    assert (
        await db.scalar(
            select(ProductionSchedulePlan.owner).where(
                ProductionSchedulePlan.order_no == "SO-SPC-LIFE"
            )
        )
        == "待重新分配"
    )
    assert (
        await db.scalar(select(PurchaseOrder.owner).where(PurchaseOrder.po_no == "PO-SPC-LIFE"))
        == "待重新分配"
    )
    assert (
        await db.scalar(
            select(QualityIssue.responsible_person).where(QualityIssue.issue_no == "QI-SPC-LIFE")
        )
        == "待重新分配"
    )


@pytest.mark.asyncio
async def test_reinstate_restores_basic_login_only_and_requires_permission_confirmation(
    lifecycle_client, db, spc_person, monkeypatch
):
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_SECRET", SECRET)
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_KEY_ID", KEY_ID)
    employee, user = spc_person
    offboard = lifecycle_event(person_id=str(employee.id), emp_code=employee.emp_code)
    reinstate = lifecycle_event(
        person_id=str(employee.id),
        emp_code=employee.emp_code,
        event_id="evt-spc-reinstate-1",
        event_type="person.reinstated",
        revision=2,
        status="active",
        employment_action="rehire",
    )

    assert (
        await post_event(lifecycle_client, offboard)
    ).status_code == 200
    response = await post_event(lifecycle_client, reinstate)

    assert response.status_code == 200
    assert response.json()["status"] == "pending_confirmation"
    assert response.json()["pending_confirmation"] == {"permissions": True, "agents": True}
    await db.refresh(user)
    assert user.is_active is True
    assert (
        await db.scalar(select(SaleOrder.owner).where(SaleOrder.order_no == "SO-SPC-LIFE"))
        == "待重新分配"
    )


@pytest.mark.asyncio
async def test_conflicting_person_id_and_emp_code_fails_closed(
    lifecycle_client, db, spc_person, monkeypatch
):
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_SECRET", SECRET)
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_KEY_ID", KEY_ID)
    employee, _ = spc_person
    await db.execute(delete(Employee).where(Employee.emp_code == "E-SPC-OTHER"))
    await db.commit()
    other = Employee(emp_code="E-SPC-OTHER", emp_name="另一人员", status=1)
    db.add(other)
    await db.commit()
    body = lifecycle_event(person_id=str(employee.id), emp_code=other.emp_code)

    response = await post_event(lifecycle_client, body)

    assert response.status_code == 409
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "人员身份冲突"
    await db.delete(other)
    await db.commit()


@pytest.mark.asyncio
async def test_replay_is_idempotent_and_invalid_hmac_is_rejected(
    lifecycle_client, db, spc_person, monkeypatch
):
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_SECRET", SECRET)
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_KEY_ID", KEY_ID)
    employee, user = spc_person
    body = lifecycle_event(person_id=str(employee.id), emp_code=employee.emp_code)

    first = await post_event(lifecycle_client, body)
    replay = await post_event(lifecycle_client, body)
    invalid_body = lifecycle_event(
        person_id=str(employee.id), emp_code=employee.emp_code, event_id="evt-spc-invalid"
    )
    invalid = await post_event(lifecycle_client, invalid_body, secret="wrong-secret")

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["duplicate"] is True
    assert invalid.status_code == 401
    await db.refresh(user)
    assert user.is_active is False
