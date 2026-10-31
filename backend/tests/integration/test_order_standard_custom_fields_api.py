"""订单标准自定义字段 API 回归测试。"""

import pytest_asyncio
from sqlalchemy import text

from tests.conftest import login

ADMIN = "admin"
BASE = "/api/v1/rules/order-standards"
CONFIG = f"{BASE}/field-configs"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def business_document_tables(_test_db):
    from app.core.database import Base, engine
    from app.models.common.business_document import (
        BusinessDocument,
        BusinessDocumentFieldConfig,
        BusinessDocumentVersion,
    )

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                BusinessDocument.__table__,
                BusinessDocumentVersion.__table__,
                BusinessDocumentFieldConfig.__table__,
            ],
        )
        await conn.execute(text(
            "ALTER TABLE business_document "
            "ADD COLUMN IF NOT EXISTS custom_fields JSONB DEFAULT '{}'::jsonb"
        ))
    yield


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def clean_business_documents(business_document_tables):
    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE business_document, business_document_version, "
            "business_document_field_config RESTART IDENTITY CASCADE"
        ))
    yield


async def create_field(client, headers, **overrides):
    payload = {
        "label": "颜色",
        "widget": "text",
        "required": False,
        "show_in_list": True,
        "sort_order": 0,
    }
    payload.update(overrides)
    return await client.post(CONFIG, headers=headers, json=payload)


async def test_custom_fields_crud_and_document_flow(client):
    headers = await login(client, ADMIN)

    text_field = await create_field(client, headers, label="颜色")
    assert text_field.status_code == 200
    text_key = text_field.json()["data"]["field_key"]

    select_field = await create_field(
        client, headers, label="等级", widget="select", options=["A", "B"]
    )
    assert select_field.status_code == 200
    select_key = select_field.json()["data"]["field_key"]

    bool_field = await create_field(client, headers, label="启用", widget="boolean")
    assert bool_field.status_code == 200
    bool_key = bool_field.json()["data"]["field_key"]

    created = await client.post(
        BASE,
        headers=headers,
        json={
            "code": "TEST-CUSTOM-001",
            "title": "自定义字段测试",
            "version_no": "V1.0",
            "custom_fields": {text_key: "红色", select_key: "A", bool_key: False},
        },
    )
    assert created.status_code == 200, created.text
    document = created.json()["data"]
    assert document["custom_fields"] == {text_key: "红色", select_key: "A", bool_key: False}

    listed = await client.get(BASE, headers=headers, params={"keyword": "TEST-CUSTOM-001"})
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["custom_fields"][text_key] == "红色"

    updated = await client.put(
        f"{BASE}/{document['id']}",
        headers=headers,
        json={"custom_fields": {text_key: "蓝色", select_key: None, bool_key: False}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["custom_fields"] == {text_key: "蓝色", bool_key: False}

    deleted_config = await client.delete(
        f"{CONFIG}/{select_field.json()['data']['id']}", headers=headers
    )
    assert deleted_config.status_code == 200

    detail = await client.get(BASE, headers=headers, params={"keyword": "TEST-CUSTOM-001"})
    assert select_key not in detail.json()["data"]["items"][0]["custom_fields"]

    deleted_doc = await client.delete(f"{BASE}/{document['id']}", headers=headers)
    assert deleted_doc.status_code == 200


async def test_required_and_type_validation(client):
    headers = await login(client, ADMIN)
    field = await create_field(client, headers, label="必填文本", required=True)
    key = field.json()["data"]["field_key"]

    missing = await client.post(
        BASE, headers=headers, json={"code": "TEST-CUSTOM-002", "title": "缺必填", "version_no": "V1.0"}
    )
    assert missing.status_code == 400

    wrong_type = await client.post(
        BASE,
        headers=headers,
        json={
            "code": "TEST-CUSTOM-003",
            "title": "类型错误",
            "version_no": "V1.0",
            "custom_fields": {key: 1},
        },
    )
    assert wrong_type.status_code == 400

    unknown = await client.post(
        BASE,
        headers=headers,
        json={
            "code": "TEST-CUSTOM-004",
            "title": "未知字段",
            "version_no": "V1.0",
            "custom_fields": {"unknown": "x"},
        },
    )
    assert unknown.status_code == 400


async def test_field_config_validation(client):
    headers = await login(client, ADMIN)

    bad_widget = await create_field(client, headers, widget="unknown")
    assert bad_widget.status_code == 400

    empty_select = await create_field(client, headers, widget="select", options=[])
    assert empty_select.status_code == 400

    first = await create_field(client, headers, label="重复名称")
    assert first.status_code == 200
    duplicate = await create_field(client, headers, label="重复名称")
    assert duplicate.status_code == 400

    updatable = await create_field(
        client, headers, label="更新前", widget="select", options=["A"]
    )
    config_id = updatable.json()["data"]["id"]
    updated = await client.put(
        f"{CONFIG}/{config_id}",
        headers=headers,
        json={
            "label": "更新后",
            "required": True,
            "show_in_list": False,
            "options": ["A", "B"],
            "sort_order": 5,
        },
    )
    assert updated.status_code == 200, updated.text
    updated_data = updated.json()["data"]
    assert updated_data["label"] == "更新后"
    assert updated_data["required"] is True
    assert updated_data["show_in_list"] is False
    assert updated_data["options"] == ["A", "B"]
    assert updated_data["sort_order"] == 5

    duplicate_update = await client.put(
        f"{CONFIG}/{config_id}", headers=headers, json={"label": "重复名称"}
    )
    assert duplicate_update.status_code == 400

    null_required = await client.put(
        f"{CONFIG}/{config_id}", headers=headers, json={"required": None}
    )
    assert null_required.status_code == 400

    null_sort = await client.put(
        f"{CONFIG}/{config_id}", headers=headers, json={"sort_order": None}
    )
    assert null_sort.status_code == 200
    assert null_sort.json()["data"]["sort_order"] == 0


async def test_field_config_requires_update_permission(client):
    headers = await login(client, "qa_viewer")
    denied = await create_field(client, headers)
    assert denied.status_code == 403
