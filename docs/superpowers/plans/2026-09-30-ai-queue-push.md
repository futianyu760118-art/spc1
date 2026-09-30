# 问题反馈派单即时送达 Runner（长轮询）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 派单（新派/重排/重试）后后端立即唤醒正在等待的 runner，`queued → running` 延迟 < 1 秒，替代 5–10 秒轮询。

**Architecture:** 新增 `GET /ai-queue-wait` 长轮询端点（模块级 `asyncio.Event` 等待者集合，派单提交后 `notify_queue_waiters()` 即时唤醒 + 1 秒复查兜底，空查询后 `rollback()` 释放连接）；runner 主循环改为挂起等待，异常时按 `poll_interval_seconds` 退避重连；前端与数据库 schema 均无改动。

**Tech Stack:** FastAPI + async SQLAlchemy（无新依赖）；Python 3.12/3.13 + httpx（runner）。

**设计文档：** `docs/superpowers/specs/2026-09-30-ai-queue-push-design.md`（一切需求以该文档为准）

## Global Constraints

- 所有后端成功响应必须 `{code, message, data}`（`ResponseModel`）；`feedback.py` 沿用显式 `await db.commit()` 写法。
- **路由顺序硬性要求**：`GET /ai-queue-wait` 必须声明在 `GET /{feedback_id}` 之前，否则会被 int 路径参数吞掉报 422。
- 长轮询等待期间不得持有 DB 连接：每次空查询后 `await db.rollback()` 再等待。
- 等待者集合为进程内机制：dev/prod compose 均单 worker（已确认 uvicorn 无 `--workers`），1 秒复查兜底覆盖异常场景。
- runner 不新增依赖、不新增配置键；`poll_interval_seconds` 语义变为"等待出错后的退避间隔"。
- 测试命令：`cd backend && D:\software\miniconda3\python.exe -m pytest`；runner 校验 `D:\software\miniconda3\python.exe -m py_compile runner.py`（本机 `python` 不在 PATH）。
- `docs/` 在 `.gitignore`，提交 docs 用 `git add -f`。
- 面向用户/运维文案用简体中文。
- 当前 runner 未在运行；`.runner.lock` 已不存在；#118 卡在 `running`（Phase D 重排）。**Phase D 重启 runner/重建容器前须经用户确认**。

---

## Phase A：后端

### Task A1: ai-queue-wait 长轮询端点与唤醒机制

**Files:**
- Modify: `backend/app/api/v1/basicdata/feedback.py`

**Interfaces:**
- Produces: `GET /api/v1/basicdata/feedback/ai-queue-wait`（返回 `data={"ids": [...]}`）、`notify_queue_waiters()`；`ai_queue_feedback` 提交后唤醒。

- [ ] **Step 1: 补 import**

把文件顶部

```python
import logging
from datetime import datetime
```

替换为：

```python
import asyncio
import logging
import time
from datetime import datetime
```

- [ ] **Step 2: 加等待者集合与辅助函数**

在 `# ---------- 列表 ----------` 注释之前插入：

```python
# ---------- AI 派单等待（长轮询） ----------
_AI_QUEUE_WAIT_DEFAULT_SECONDS = 20
_AI_QUEUE_WAIT_MAX_IDS = 10
_AI_QUEUE_WAIT_RECHECK_SECONDS = 1.0
_queue_waiters: set[asyncio.Event] = set()


def notify_queue_waiters() -> None:
    """派单提交后唤醒所有等待中的长轮询请求（毫秒级送达 runner）。"""
    for waiter in list(_queue_waiters):
        waiter.set()


async def _list_queued_ids(db: AsyncSession, limit: int) -> list[int]:
    rows = (await db.execute(
        select(Feedback.id)
        .where(Feedback.ai_status == "queued")
        .order_by(Feedback.created_at.asc())
        .limit(limit)
    )).scalars().all()
    return [int(row) for row in rows]
```

- [ ] **Step 3: 加长轮询端点（必须在 `GET /{feedback_id}` 之前）**

在 `# ---------- 详情 ----------` 注释之前、`list_feedback` 端点之后插入：

```python
@router.get("/ai-queue-wait", response_model=ResponseModel[dict])
async def ai_queue_wait(
    timeout_seconds: float = Query(_AI_QUEUE_WAIT_DEFAULT_SECONDS, ge=1, le=30),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """长轮询等待待派反馈：有任务立即返回，无任务挂起至多 timeout_seconds。

    注意：本路由必须声明在 `GET /{feedback_id}` 之前，否则会被 int 路径参数吞掉。
    """
    if not _can_handle(current_user):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    waiter = asyncio.Event()
    _queue_waiters.add(waiter)
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            ids = await _list_queued_ids(db, _AI_QUEUE_WAIT_MAX_IDS)
            await db.rollback()  # 只读事务结束，长轮询不占用连接
            if ids:
                return ResponseModel(data={"ids": ids})
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ResponseModel(data={"ids": []})
            try:
                await asyncio.wait_for(
                    waiter.wait(),
                    timeout=min(_AI_QUEUE_WAIT_RECHECK_SECONDS, remaining),
                )
            except asyncio.TimeoutError:
                pass
            waiter.clear()
    finally:
        _queue_waiters.discard(waiter)
```

- [ ] **Step 4: 派单后唤醒等待者**

在 `ai_queue_feedback` 的 `await db.refresh(fb)` 之后、`return ResponseModel(...)` 之前插入：

```python
    notify_queue_waiters()
```

- [ ] **Step 5: 验证路由顺序与导入**

在 `backend/` 下执行：

```powershell
D:\software\miniconda3\python.exe -c "from app.main import app; rs=[r.path for r in app.routes if 'ai-queue-wait' in getattr(r,'path','')]; print(rs); i=[r.path for r in app.routes].index('/api/v1/basicdata/feedback/ai-queue-wait'); j=[r.path for r in app.routes].index('/api/v1/basicdata/feedback/{feedback_id}'); print('order ok:', i < j)"
```

Expected: 打印路由存在且 `order ok: True`。

- [ ] **Step 6: Commit**

```powershell
git add backend/app/api/v1/basicdata/feedback.py
git commit -m "feat(feedback): ai-queue-wait 长轮询端点 + 派单即时唤醒"
```

---

### Task A2: 长轮询集成测试

**Files:**
- Modify: `backend/tests/integration/test_feedback_ai_api.py`

**Interfaces:**
- Consumes: A1 端点。
- Produces: 覆盖立即返回 / 唤醒 / 超时 / 权限 4 场景。

- [ ] **Step 1: 加 asyncio import**

在文件顶部 `from tests.conftest import login` 之前插入：

```python
import asyncio
```

- [ ] **Step 2: 追加 4 个用例**

在文件末尾追加：

```python
async def test_ai_queue_wait_returns_existing(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="等待-已有任务")
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)

    r = await client.get(
        "/api/v1/basicdata/feedback/ai-queue-wait",
        params={"timeout_seconds": 5},
        headers=headers,
    )
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["ids"] == [fb["id"]]


async def test_ai_queue_wait_wakes_on_dispatch(client):
    headers = await login(client, "admin")
    fb = await _create_feedback(client, headers, title="等待-派单唤醒")

    loop = asyncio.get_running_loop()
    started = loop.time()
    wait_task = asyncio.create_task(client.get(
        "/api/v1/basicdata/feedback/ai-queue-wait",
        params={"timeout_seconds": 5},
        headers=headers,
    ))
    await asyncio.sleep(0.2)
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    r = await wait_task
    elapsed = loop.time() - started

    assert r.json()["data"]["ids"] == [fb["id"]]
    assert elapsed < 3  # 证明是唤醒返回而非 5s 超时兜底


async def test_ai_queue_wait_timeout_returns_empty(client):
    headers = await login(client, "admin")
    r = await client.get(
        "/api/v1/basicdata/feedback/ai-queue-wait",
        params={"timeout_seconds": 1},
        headers=headers,
    )
    assert r.json()["data"]["ids"] == []


async def test_ai_queue_wait_requires_handle_permission(client):
    viewer_headers = await login(client, "qa_viewer")
    r = await client.get(
        "/api/v1/basicdata/feedback/ai-queue-wait",
        params={"timeout_seconds": 1},
        headers=viewer_headers,
    )
    assert r.status_code == 403
```

- [ ] **Step 3: 跑新测试**

Run（在 `backend/` 下）：

```powershell
D:\software\miniconda3\python.exe -m pytest tests/integration/test_feedback_ai_api.py -v
```

Expected: 全部 passed（含 4 个新用例）。

- [ ] **Step 4: 跑全量回归**

Run（在 `backend/` 下）：

```powershell
D:\software\miniconda3\python.exe -m pytest -q
```

Expected: 除 2 个既有无关收集错误（`test_external_freshness_api.py` / `test_external_production_api.py`，ImportError: iso_aware）外全部通过；如有新增失败必须修复。

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/integration/test_feedback_ai_api.py
git commit -m "test(feedback): ai-queue-wait 长轮询用例（立即返回/唤醒/超时/权限）"
```

---

## Phase B：Runner

### Task B1: 主循环改长轮询等待

**Files:**
- Modify: `scripts/ai-feedback-runner/runner.py`

**Interfaces:**
- Consumes: A1 端点。
- Produces: `ApiClient.wait_queued`；主循环挂起等待；删除 `list_queued`。

- [ ] **Step 1: 加常量与 wait_queued**

在 `PROGRESS_REQUEST_TIMEOUT_SECONDS = 5.0` 之后插入：

```python
WAIT_TIMEOUT_SECONDS = 20
```

在 `ApiClient` 中删除 `list_queued` 方法（已无调用），并在 `finish` 方法之后插入：

```python
    def wait_queued(self, timeout_seconds: int) -> list[int]:
        response = self._request(
            "GET",
            "/api/v1/basicdata/feedback/ai-queue-wait",
            params={"timeout_seconds": timeout_seconds},
            timeout=timeout_seconds + 10,
        )
        body = self._json(response)
        if body.get("code") != 0:
            raise RuntimeError(f"等待队列失败: {body.get('message')}")
        return list(body["data"].get("ids") or [])
```

- [ ] **Step 2: 改造主循环**

把 `main()` 中从 `log(f"Runner 启动: ...")` 到 `process_feedback(cfg, api, claimed)` 的整段循环替换为：

```python
        log(
            f"Runner 启动: {cfg['base_url']}，长轮询等待（超时 {WAIT_TIMEOUT_SECONDS}s，"
            f"出错退避 {cfg['poll_interval_seconds']}s）"
        )
        while not STOP["requested"]:
            try:
                ids = api.wait_queued(2 if args.once else WAIT_TIMEOUT_SECONDS)
            except Exception as exc:
                log(f"等待队列失败: {exc}")
                wait_for(cfg["poll_interval_seconds"])
                continue
            if not ids:
                if args.once:
                    log("队列为空，退出（--once）")
                    return
                continue
            for feedback_id in ids:
                if STOP["requested"]:
                    break
                try:
                    claimed = api.claim(feedback_id)
                except Exception as exc:
                    log(f"认领反馈 #{feedback_id} 失败: {exc}")
                    claimed = None
                if not claimed:
                    continue
                process_feedback(cfg, api, claimed)
```

- [ ] **Step 3: 更新 docstring 机制描述**

把模块 docstring 第二行：

```python
轮询后端问题反馈队列（ai_status=queued），认领后：
```

替换为：

```python
长轮询等待后端问题反馈队列（ai_status=queued），认领后：
```

- [ ] **Step 4: 语法与残留检查**

Run（在 `scripts/ai-feedback-runner/` 下）：

```powershell
D:\software\miniconda3\python.exe -m py_compile runner.py
Select-String -Path runner.py -Pattern 'list_queued'
```

Expected: py_compile 无输出；`list_queued` 无匹配。

- [ ] **Step 5: Commit**

```powershell
git add scripts/ai-feedback-runner/runner.py
git commit -m "feat(ai-runner): 主循环改 ai-queue-wait 长轮询等待，删除 list_queued"
```

---

## Phase C：端到端验证（需用户确认后执行）

### Task C1: 重建后端、重启 runner、重排 #118 并实测

**Files:** 无代码改动。

- [ ] **Step 1: 重建并重启后端容器**

```powershell
docker compose build backend
docker compose up -d backend
Start-Sleep -Seconds 8
```

（无 schema 变更，无需跑迁移；frontend 无改动，不用重建。）

- [ ] **Step 2: 启动新 runner**

```powershell
Start-Process -FilePath "D:\software\miniconda3\python.exe" -ArgumentList "runner.py" -WorkingDirectory "D:\wanghuazheng\project\SPC-v2\scripts\ai-feedback-runner" -WindowStyle Minimized
Start-Sleep -Seconds 4
Get-Content scripts\ai-feedback-runner\.runner.lock
```

Expected: 锁文件写入新 PID；无旧锁残留。

- [ ] **Step 3: 重排 #118 并测延迟**

1. 先看 #118 当前状态（应为 `ai_status=running`，卡住状态）；
2. 对其 `POST /ai-queue`（允许 running 重排 → queued）；
3. 从 POST 返回后以 0.2s 间隔轮询详情，直到 `ai_status=running`，记录耗时。

Expected: 认领延迟 **< 1 秒**（长轮询唤醒路径）；#118 开始重新执行并可观察到 `preparing → agent → …` 阶段推进。

- [ ] **Step 4: 观察至跑完**

Expected: #118 产出 `ai-feedback/118` 分支、进度历史完整、`ai_status=done`（或留下可读失败原因）。
