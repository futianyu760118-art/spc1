"""问题反馈 AI 自动实现 API 状态机测试（ai-queue / ai-claim / ai-finish）。"""

from tests.conftest import login


async def _create_feedback(client, headers, **overrides):
    payload = {
        "type": "issue",
        "severity": "medium",
        "page_path": "/demo",
        "title": "示例反馈",
        "description": "示例描述",
        **overrides,
    }
    response = await client.post("/api/v1/basicdata/feedback", json=payload, headers=headers)
    body = response.json()
    assert body.get("code") == 0, body
    return body["data"]


async def test_ai_queue_and_cancel(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="派单与取消")

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["ai_status"] == "queued"
    assert body["data"]["status"] == "processing"
    assert body["data"]["ai_requested_by"] == "admin"

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    assert r.status_code == 400

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-cancel", headers=headers)
    assert r.json()["data"]["ai_status"] == "none"


async def test_ai_claim_finish_lifecycle(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="认领与完成")
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)
    assert r.json()["data"]["ai_status"] == "running"

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)
    assert r.status_code == 409

    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish",
        json={"success": True, "branch": f"ai-feedback/{fb['id']}", "summary": "pytest/build 通过"},
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["ai_status"] == "done"
    assert body["data"]["ai_branch"] == f"ai-feedback/{fb['id']}"
    assert "AI 自动实现待审核" in body["data"]["reply"]

    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish",
        json={"success": True},
        headers=headers,
    )
    assert r.status_code == 409


async def test_ai_finish_requires_running(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="未认领直接回写")
    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish",
        json={"success": False, "error": "x"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_requeue_discards_stale_result(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="重新排队丢弃旧结果")
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    assert r.json()["data"]["ai_status"] == "queued"

    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish",
        json={"success": True},
        headers=headers,
    )
    assert r.status_code == 409


async def test_ai_queue_rejected_for_resolved(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="已解决不可派单")
    await client.patch(
        f"/api/v1/basicdata/feedback/{fb['id']}/status",
        json={"status": "resolved"},
        headers=headers,
    )
    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    assert r.status_code == 400


async def test_ai_endpoints_require_handle_permission(client):
    admin_headers = await login(client, "admin")
    viewer_headers = await login(client, "qa_viewer")
    fb = await _create_feedback(client, admin_headers, title="权限校验")

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=viewer_headers)
    assert r.status_code == 403
    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-cancel", headers=viewer_headers)
    assert r.status_code == 403
    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=viewer_headers)
    assert r.status_code == 403
    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish", json={"success": False, "error": "x"}, headers=viewer_headers)
    assert r.status_code == 403


async def test_list_filter_by_ai_status(client):
    headers = await login(client, "admin")
    fb_queued = await _create_feedback(client, headers, title="筛选-排队")
    await _create_feedback(client, headers, title="筛选-未派单")
    await client.post(f"/api/v1/basicdata/feedback/{fb_queued['id']}/ai-queue", headers=headers)

    r = await client.get(
        "/api/v1/basicdata/feedback",
        params={"ai_status": "queued"},
        headers=headers,
    )
    items = r.json()["data"]["items"]
    assert [item["id"] for item in items] == [fb_queued["id"]]
