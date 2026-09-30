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


async def _queue_and_claim(client, headers, **overrides):
    fb = await _create_feedback(client, headers, **overrides)
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)
    assert r.json()["data"]["ai_status"] == "running"
    return fb


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


async def test_ai_finish_failure_then_retry(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="失败回写后重试")
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)

    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish",
        json={"success": False, "error": "代理执行超时"},
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["ai_status"] == "failed"
    assert body["data"]["ai_note"] == "代理执行超时"
    assert "AI 自动实现失败" in body["data"]["reply"]

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    assert r.json()["data"]["ai_status"] == "queued"


async def test_ai_queue_rejected_for_done(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="已完成不可重新派单")
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)
    await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish",
        json={"success": True},
        headers=headers,
    )

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    assert r.status_code == 400


async def test_ai_finish_with_long_summary_clips_notification(client):
    """超长实现摘要只允许截断写入通知，不得触发 500（notification.content varchar(512)）。"""
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="长摘要回写")
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)

    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish",
        json={
            "success": True,
            "branch": f"ai-feedback/{fb['id']}",
            "summary": "验证说明" * 400,
        },
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["ai_status"] == "done"
    assert body["data"]["ai_branch"] == f"ai-feedback/{fb['id']}"


async def test_reply_with_long_text_clips_notification(client):
    """人工长回复同样只截断通知内容，不得 500。"""
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="长回复")

    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/reply",
        json={"reply": "处理结论" * 300},
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["reply"].startswith("处理结论")


async def test_ai_progress_requires_running(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="进度-未认领")
    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-progress",
        json={"stage": "agent"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_ai_progress_stage_and_actions(client):
    headers = await login(client, "admin")
    fb = await _queue_and_claim(client, headers, title="进度-阶段与动作")
    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-progress",
        json={"stage": "agent", "actions": ["读取 a.tsx", "修改 a.tsx"]},
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["ai_stage"] == "agent"

    r = await client.get(f"/api/v1/basicdata/feedback/{fb['id']}", headers=headers)
    data = r.json()["data"]
    assert data["ai_stage"] == "agent"
    assert data["ai_stage_started_at"] is not None
    assert [e["kind"] for e in data["ai_progress"]] == ["stage", "action", "action"]
    assert data["ai_progress"][0]["text"] == "AI 修改代码"
    assert data["ai_progress"][2]["stage"] == "agent"


async def test_ai_progress_validation_and_trim(client):
    headers = await login(client, "admin")
    fb = await _queue_and_claim(client, headers, title="进度-校验与裁剪")

    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-progress",
        json={"stage": "unknown"},
        headers=headers,
    )
    assert r.status_code == 400
    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-progress",
        json={"actions": ["   "]},
        headers=headers,
    )
    assert r.status_code == 400

    long_text = "x" * 500
    for _ in range(3):
        r = await client.post(
            f"/api/v1/basicdata/feedback/{fb['id']}/ai-progress",
            json={"actions": [long_text] * 30},
            headers=headers,
        )
        assert r.json()["code"] == 0
    r = await client.get(f"/api/v1/basicdata/feedback/{fb['id']}", headers=headers)
    entries = r.json()["data"]["ai_progress"]
    assert len(entries) == 50
    assert len(entries[-1]["text"]) == 200


async def test_ai_progress_requires_handle_permission(client):
    admin_headers = await login(client, "admin")
    viewer_headers = await login(client, "qa_viewer")
    fb = await _create_feedback(client, admin_headers, title="进度-权限")
    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-progress",
        json={"stage": "agent"},
        headers=viewer_headers,
    )
    assert r.status_code == 403


async def test_requeue_clears_progress_and_finish_keeps_it(client):
    headers = await login(client, "admin")
    fb = await _queue_and_claim(client, headers, title="进度-重排与完成")
    await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-progress",
        json={"stage": "agent", "actions": ["修改 a.tsx"]},
        headers=headers,
    )

    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    data = r.json()["data"]
    assert data["ai_status"] == "queued"
    assert data["ai_progress"] is None
    assert data["ai_stage"] is None

    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)
    await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-progress",
        json={"stage": "gate_backend"},
        headers=headers,
    )
    r = await client.post(
        f"/api/v1/basicdata/feedback/{fb['id']}/ai-finish",
        json={"success": True, "branch": f"ai-feedback/{fb['id']}", "summary": "ok"},
        headers=headers,
    )
    data = r.json()["data"]
    assert data["ai_status"] == "done"
    assert data["ai_stage"] is None
    assert data["ai_stage_started_at"] is None
    assert len(data["ai_progress"]) == 1
    assert data["ai_progress"][0]["stage"] == "gate_backend"
