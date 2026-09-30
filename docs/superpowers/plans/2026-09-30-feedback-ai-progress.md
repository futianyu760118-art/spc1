# 问题反馈 AI 实现进度可视化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI 实现反馈的 `running` 期间，详情抽屉实时展示阶段时间轴与 claude 动作流，不再只有一个「实现中」黑盒状态。

**Architecture:** `feedback` 行加 3 个进度列（ai_stage / ai_stage_started_at / ai_progress JSONB）；后端加 `ai-progress` 上报端点（仅 running 接受）；runner 把 claude 调用改为 `stream-json` 流式解析，把 `tool_use` 转写为中文动作并节流上报（失败静默降级）；前端抽屉渲染阶段时间轴 + 动作列表，并让抽屉快照跟随列表 15s 轮询同步。

**Tech Stack:** FastAPI + async SQLAlchemy + PostgreSQL（JSONB）；React 18 + Ant Design 5 + TypeScript；Python 3.12/3.13 + httpx（runner）；claude CLI 2.1.284（`-p --output-format stream-json --verbose`）。

**设计文档：** `docs/superpowers/specs/2026-09-30-feedback-ai-progress-design.md`（一切需求以该文档为准）

## Global Constraints

- 新列必须**同时**登记在 SQLAlchemy model 与 `backend/init_database.py` 的 `migrate_columns["feedback"]`（现有条目在 L427 附近），否则容器重启后列不存在。
- 所有后端成功响应必须 `{code, message, data}`（`ResponseModel`）；`feedback.py` 模块沿用既有「显式 `await db.commit()`」写法。
- 进度上报是**尽力而为**：runner 侧任何上报异常只记日志、不改任务结果；后端对非 running 上报返回 409 直接丢弃。
- 不新增第三方依赖、不新增 runner 配置项（节流间隔用代码常量）。
- `claude -p --output-format stream-json` 必须同时带 `--verbose`（CLI 2.1.284 已确认），否则 CLI 报错。
- 前端校验唯一命令 `cd frontend && npm run build`；后端测试 `cd backend && python -m pytest`（本机解释器 `D:\software\miniconda3\python.exe`）。
- `docs/` 在 `.gitignore` 中；提交 docs 下文件需 `git add -f`。
- 所有面向用户的文案用简体中文；UI 复用反馈管理页现有 class（`sc-tag` / `sc-note` / `sc-mono` / `DrawerSection`）。
- 当前有常驻旧 runner（PID 22592，`.runner.lock` 指向它）在运行：改 `runner.py` 不影响它，Phase D 重启步骤**执行前必须经用户确认**。
- 每完成一个 Task 提交一次 commit，提交信息见各 Task。

---

## Phase A：后端

### Task A1: feedback 模型与迁移加 3 列

**Files:**
- Modify: `backend/app/models/basicdata/feedback.py`
- Modify: `backend/init_database.py`

**Interfaces:**
- Produces: `feedback` 表新列 `ai_stage` / `ai_stage_started_at` / `ai_progress`，供后续 schema/API 使用。

- [ ] **Step 1: 给模型加列**

在 `backend/app/models/basicdata/feedback.py` 的 `ai_requested_at` 行之后插入：

```python
    ai_stage = Column(String(32), nullable=True,
                      comment="当前阶段（preparing/fetching/agent/gate_backend/gate_frontend/committing）")
    ai_stage_started_at = Column(DateTime, nullable=True, comment="当前阶段开始时间")
    ai_progress = Column(JSONB, nullable=True, comment="执行记录 [{at,kind,stage,text}]，保留最近 50 条")
```

- [ ] **Step 2: 登记到 init_database.py**

在 `backend/init_database.py` L427 的 `"feedback"` 条目中，`"ai_requested_at": "TIMESTAMP",` 之后插入：

```python
                "ai_stage": "VARCHAR(32)",
                "ai_stage_started_at": "TIMESTAMP",
                "ai_progress": "JSONB",
```

- [ ] **Step 3: 验证迁移幂等**

在 `backend/` 下执行：

```powershell
D:\software\miniconda3\python.exe init_database.py
D:\software\miniconda3\python.exe init_database.py
```

Expected: 两次均正常结束；日志中不出现 `feedback.ai_* skipped`。

- [ ] **Step 4: Commit**

```powershell
git add backend/app/models/basicdata/feedback.py backend/init_database.py
git commit -m "feat(feedback): AI 进度 3 列（ai_stage/ai_stage_started_at/ai_progress）+ 迁移登记"
```

---

### Task A2: schemas 扩展

**Files:**
- Modify: `backend/app/schemas/basicdata/feedback.py`

**Interfaces:**
- Produces: `FeedbackAiProgress`（上报请求体）与 `FeedbackOut` 的 3 个进度字段，供 Task A3 / A4 使用。

- [ ] **Step 1: 新增请求 schema**

在 `FeedbackAiFinish` 类之后插入：

```python
class FeedbackAiProgress(BaseModel):
    stage: Optional[str] = None          # 阶段 key，白名单校验
    actions: Optional[List[str]] = None  # 动作批，单次最多 20 条
```

- [ ] **Step 2: FeedbackOut 加输出字段**

在 `FeedbackOut` 的 `ai_requested_at` 行之后插入：

```python
    ai_stage: Optional[str] = None
    ai_stage_started_at: Optional[datetime] = None
    ai_progress: Optional[List[Any]] = None
```

- [ ] **Step 3: 验证导入**

Run（在 `backend/` 下）：

```powershell
D:\software\miniconda3\python.exe -c "from app.schemas.basicdata.feedback import FeedbackAiProgress, FeedbackOut; print('ok')"
```

Expected: 输出 `ok`。

- [ ] **Step 4: Commit**

```powershell
git add backend/app/schemas/basicdata/feedback.py
git commit -m "feat(feedback): FeedbackAiProgress schema + FeedbackOut 进度字段"
```

---

### Task A3: ai-progress 端点 + ai-queue/ai-finish 进度清理

**Files:**
- Modify: `backend/app/api/v1/basicdata/feedback.py`

**Interfaces:**
- Consumes: `FeedbackAiProgress`（A2）、`Feedback` 新列（A1）。
- Produces: `POST /api/v1/basicdata/feedback/{id}/ai-progress`；派单清空进度；完成保留历史、清空当前阶段。

- [ ] **Step 1: 更新 schema import**

把 import 块中的

```python
from app.schemas.basicdata.feedback import (
    FeedbackAiFinish,
```

替换为：

```python
from app.schemas.basicdata.feedback import (
    FeedbackAiFinish,
    FeedbackAiProgress,
```

- [ ] **Step 2: 加阶段常量**

在 `_AI_TERMINAL_STATUSES = ("resolved", "closed")` 之后插入：

```python
_AI_STAGE_LABELS = {
    "preparing": "准备隔离环境",
    "fetching": "下载附件",
    "agent": "AI 修改代码",
    "gate_backend": "后端测试",
    "gate_frontend": "前端构建",
    "committing": "提交代码",
}
_AI_PROGRESS_MAX_ENTRIES = 50
_AI_PROGRESS_MAX_ACTIONS_PER_POST = 20
_AI_PROGRESS_ACTION_MAX_LEN = 200
```

- [ ] **Step 3: 新增 ai-progress 端点**

在 `ai_claim_feedback` 端点之后、`ai_finish_feedback` 之前插入：

```python
@router.post("/{feedback_id}/ai-progress", response_model=ResponseModel[dict])
async def ai_progress_feedback(
    feedback_id: int,
    body: FeedbackAiProgress,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Runner 上报执行进度：仅 running 接受；stage 白名单；动作截断并裁剪历史。"""
    if not _can_handle(current_user):
        raise HTTPException(status_code=403, detail="无权处理反馈")

    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id).with_for_update()
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if fb.ai_status != "running":
        raise HTTPException(status_code=409, detail=f"反馈当前状态为 {fb.ai_status}，拒绝上报进度")

    actions: list[str] = []
    for raw in body.actions or []:
        text = (raw or "").strip()
        if not text:
            continue
        actions.append(text[:_AI_PROGRESS_ACTION_MAX_LEN])
        if len(actions) >= _AI_PROGRESS_MAX_ACTIONS_PER_POST:
            break
    if not body.stage and not actions:
        raise HTTPException(status_code=400, detail="stage 和 actions 至少填一项")
    if body.stage and body.stage not in _AI_STAGE_LABELS:
        raise HTTPException(status_code=400, detail=f"非法阶段: {body.stage}")

    entries = list(fb.ai_progress or [])
    now_iso = datetime.now().isoformat(timespec="seconds")
    if body.stage:
        fb.ai_stage = body.stage
        fb.ai_stage_started_at = datetime.now()
        entries.append({
            "at": now_iso,
            "kind": "stage",
            "stage": body.stage,
            "text": _AI_STAGE_LABELS[body.stage],
        })
    for text in actions:
        entries.append({"at": now_iso, "kind": "action", "stage": fb.ai_stage, "text": text})
    fb.ai_progress = entries[-_AI_PROGRESS_MAX_ENTRIES:]

    await db.commit()
    await db.refresh(fb)
    return ResponseModel(data={"ai_status": fb.ai_status, "ai_stage": fb.ai_stage})
```

- [ ] **Step 4: 派单清空进度**

在 `ai_queue_feedback` 中 `fb.ai_status = "queued"` 之后插入：

```python
    fb.ai_progress = None
    fb.ai_stage = None
    fb.ai_stage_started_at = None
```

- [ ] **Step 5: 完成保留历史、清空当前阶段**

在 `ai_finish_feedback` 的 `if body.success: ... else: ...` 块之后、`fb.reply = reply_text` 之前插入：

```python
    fb.ai_stage = None
    fb.ai_stage_started_at = None
```

- [ ] **Step 6: 验证导入与路由**

Run（在 `backend/` 下）：

```powershell
D:\software\miniconda3\python.exe -c "from app.main import app; print([r.path for r in app.routes if 'ai-' in getattr(r, 'path', '')])"
```

Expected: 输出包含 5 条路径（`.../ai-queue`、`.../ai-cancel`、`.../ai-claim`、`.../ai-progress`、`.../ai-finish`）。

- [ ] **Step 7: Commit**

```powershell
git add backend/app/api/v1/basicdata/feedback.py
git commit -m "feat(feedback): ai-progress 进度上报端点 + 派单/完成进度清理"
```

---

### Task A4: 进度端点集成测试

**Files:**
- Modify: `backend/tests/integration/test_feedback_ai_api.py`

**Interfaces:**
- Consumes: A3 端点、A2 schema。
- Produces: 覆盖 409/403/400/裁剪/清空/保留历史的用例。

- [ ] **Step 1: 加测试辅助函数**

在 `_create_feedback` 之后插入：

```python
async def _queue_and_claim(client, headers, **overrides):
    fb = await _create_feedback(client, headers, **overrides)
    await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-queue", headers=headers)
    r = await client.post(f"/api/v1/basicdata/feedback/{fb['id']}/ai-claim", headers=headers)
    assert r.json()["data"]["ai_status"] == "running"
    return fb
```

- [ ] **Step 2: 追加 6 个用例**

在文件末尾追加：

```python
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
```

- [ ] **Step 3: 跑新测试**

Run（在 `backend/` 下）：

```powershell
D:\software\miniconda3\python.exe -m pytest tests/integration/test_feedback_ai_api.py -v
```

Expected: 全部 passed（新增 6 个用例 + 既有用例）。

- [ ] **Step 4: 跑全量回归**

Run（在 `backend/` 下）：

```powershell
D:\software\miniconda3\python.exe -m pytest -q
```

Expected: 全部通过（无 failed）。若出现与本次无关的既有失败，记录到交付说明中。

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/integration/test_feedback_ai_api.py
git commit -m "test(feedback): ai-progress 进度端点集成测试（校验/裁剪/清空/保留历史）"
```

---

## Phase B：Runner

### Task B1: 进度上报客户端 + 节流 ProgressReporter

**Files:**
- Modify: `scripts/ai-feedback-runner/runner.py`

**Interfaces:**
- Consumes: A3 端点。
- Produces: `ApiClient.progress()`、`ProgressReporter`（`stage` / `action` / `flush`），供 Task B3 使用。

- [ ] **Step 1: 加 import 与常量**

在 `import subprocess` 之后插入 `import threading`；在 `STOP = {"requested": False}` 之后插入：

```python
PROGRESS_FLUSH_SECONDS = 5.0
PROGRESS_MAX_ACTIONS_PER_POST = 20
```

- [ ] **Step 2: （input_text 清理已移至 B2）**

`run_command` 的 `input_text` 参数清理与 `invoke_claude` 重写强耦合（避免本提交运行期断裂），合并到 Task B2 Step 2 一起执行。

- [ ] **Step 3: ApiClient 加 progress 方法**

在 `ApiClient.finish` 方法之后插入：

```python
    def progress(self, feedback_id: int, stage: str | None = None,
                 actions: list[str] | None = None) -> None:
        payload: dict = {}
        if stage:
            payload["stage"] = stage
        if actions:
            payload["actions"] = actions
        response = self._request(
            "POST",
            f"/api/v1/basicdata/feedback/{feedback_id}/ai-progress",
            json=payload,
        )
        body = self._json(response)
        if body.get("code") != 0:
            raise RuntimeError(f"进度上报失败: {body.get('message')}")
```

- [ ] **Step 4: 加 ProgressReporter**

在 `ApiClient.close` 之后插入：

```python
class ProgressReporter:
    """AI 进度上报（尽力而为）：阶段即时上报，动作节流批量上报；失败只记日志。"""

    def __init__(self, api: ApiClient, feedback_id: int):
        self._api = api
        self._feedback_id = feedback_id
        self._buffer: list[str] = []
        self._last_flush = time.monotonic()

    def stage(self, name: str) -> None:
        self.flush()
        self._post(stage=name)

    def action(self, text: str) -> None:
        self._buffer.append(text)
        if len(self._buffer) >= PROGRESS_MAX_ACTIONS_PER_POST:
            self.flush()
        elif time.monotonic() - self._last_flush >= PROGRESS_FLUSH_SECONDS:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        batch, self._buffer = self._buffer, []
        self._last_flush = time.monotonic()
        self._post(actions=batch)

    def _post(self, stage: str | None = None, actions: list[str] | None = None) -> None:
        try:
            self._api.progress(self._feedback_id, stage=stage, actions=actions)
        except Exception as exc:
            log(f"进度上报失败（不影响任务）: {exc}")
```

- [ ] **Step 5: 语法校验**

Run（在 `scripts/ai-feedback-runner/` 下）：

```powershell
D:\software\miniconda3\python.exe -m py_compile runner.py
```

Expected: 无输出（编译通过）。

- [ ] **Step 6: Commit**

```powershell
git add scripts/ai-feedback-runner/runner.py
git commit -m "feat(ai-runner): 进度上报客户端与节流 ProgressReporter"
```

---

### Task B2: claude 流式调用与工具动作转写

**Files:**
- Modify: `scripts/ai-feedback-runner/runner.py`

**Interfaces:**
- Produces: `describe_tool_use(block)`、`_parse_stream_line(line)`、`_kill_process_tree(proc)`；`invoke_claude(cfg, worktree, prompt, run_dir, on_action=None)` 改为流式解析。

- [ ] **Step 1: 用流式解析工具替换 parse_claude_output**

删除 `parse_claude_output` 函数，原位置替换为：

```python
_TOOL_VERBS = {
    "Read": "读取",
    "Edit": "修改",
    "Write": "新建",
    "NotebookEdit": "修改",
    "Grep": "搜索",
    "Glob": "查找文件",
    "Task": "启动子任务",
    "Agent": "启动子任务",
}


def describe_tool_use(block: dict) -> str | None:
    """把 claude stream-json 的 tool_use 块转写为一行中文动作。"""
    name = block.get("name") or ""
    tool_input = block.get("input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if name == "Bash":
        command = str(tool_input.get("command") or "").strip().replace("\n", " ")
        return f"执行命令：{command[:120]}" if command else "执行命令"
    if name in ("Read", "Edit", "Write"):
        target = tool_input.get("file_path")
    elif name == "NotebookEdit":
        target = tool_input.get("notebook_path")
    elif name in ("Grep", "Glob"):
        target = tool_input.get("pattern")
    else:
        target = None
    verb = _TOOL_VERBS.get(name)
    if verb and target:
        return f"{verb} {target}"
    if verb:
        return verb
    return f"使用工具 {name}" if name else None


def _parse_stream_line(line: str) -> dict | None:
    """解析一行 stream-json 事件；不关心的事件返回 None。"""
    text = (line or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    event_type = payload.get("type")
    if event_type == "assistant":
        content = (payload.get("message") or {}).get("content") or []
        return {
            "type": "assistant",
            "content": [b for b in content if isinstance(b, dict)],
        }
    if event_type == "result":
        return {
            "type": "result",
            "is_error": payload.get("is_error"),
            "result": payload.get("result"),
        }
    return None
```

- [ ] **Step 2: 重写 invoke_claude（同时清理 run_command 的 input_text）**

把现有 `invoke_claude` 函数整体替换为下方代码；同时删除 `run_command` 签名中的 `input_text=None, ` 与函数体里的 `input=input_text,`（本步重写后已无调用点）。

```python
def _kill_process_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        result = run_command(["taskkill", "/F", "/T", "/PID", str(proc.pid)], check=False)
        if result.returncode == 0:
            return
    proc.kill()


def invoke_claude(cfg: dict, worktree: Path, prompt: str, run_dir: Path,
                  on_action=None) -> dict:
    claude_cfg = cfg["claude"]
    parts = [claude_cfg["command"], "-p", "--output-format", "stream-json", "--verbose"]
    if claude_cfg["dangerously_skip_permissions"]:
        parts.append("--dangerously-skip-permissions")
    else:
        parts += ["--permission-mode", claude_cfg["permission_mode"]]
        if claude_cfg["allowed_tools"]:
            parts += ["--allowedTools", ",".join(claude_cfg["allowed_tools"])]
    log(f"调用代理: {' '.join(parts)}（超时 {claude_cfg['timeout_minutes']} 分钟）")

    timed_out = threading.Event()
    parsed: dict | None = None
    output_path = run_dir / "claude-output.txt"
    stderr_path = run_dir / "claude-stderr.txt"

    def kill_on_timeout() -> None:
        timed_out.set()
        _kill_process_tree(proc)

    with output_path.open("w", encoding="utf-8") as output_file, \
            stderr_path.open("w", encoding="utf-8") as stderr_file:
        proc = subprocess.Popen(
            parts,
            cwd=str(worktree),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        watchdog = threading.Timer(claude_cfg["timeout_minutes"] * 60, kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            for line in proc.stdout:
                output_file.write(line)
                payload = _parse_stream_line(line)
                if payload is None:
                    continue
                if payload["type"] == "assistant":
                    for block in payload["content"]:
                        if block.get("type") == "tool_use":
                            action_text = describe_tool_use(block)
                            if action_text and on_action:
                                on_action(action_text)
                elif payload["type"] == "result":
                    parsed = {
                        "is_error": bool(payload.get("is_error")),
                        "result": str(payload.get("result") or ""),
                    }
            proc.wait()
        finally:
            watchdog.cancel()
            if proc.poll() is None:
                _kill_process_tree(proc)
                proc.wait()

    if timed_out.is_set():
        raise RunFailure(
            f"代理执行超时（>{claude_cfg['timeout_minutes']} 分钟），日志: {run_dir}"
        )
    if parsed is None:
        raise RunFailure(
            f"代理输出无法解析（退出码 {proc.returncode}），原始输出见 {output_path}"
        )
    return parsed
```

- [ ] **Step 3: 语法校验**

Run（在 `scripts/ai-feedback-runner/` 下）：

```powershell
D:\software\miniconda3\python.exe -m py_compile runner.py
```

Expected: 无输出（编译通过）。

- [ ] **Step 4: Commit**

```powershell
git add scripts/ai-feedback-runner/runner.py
git commit -m "feat(ai-runner): claude stream-json 流式解析 + tool_use 动作转写 + 超时看门狗"
```

---

### Task B3: 阶段上报接入处理流程

**Files:**
- Modify: `scripts/ai-feedback-runner/runner.py`

**Interfaces:**
- Consumes: `ProgressReporter`（B1）、流式 `invoke_claude`（B2）。
- Produces: `process_feedback` 与 `run_gates` 按阶段上报进度。

- [ ] **Step 1: run_gates 增加 progress 参数**

把 `run_gates` 签名（`files: list[str], run_dir: Path, ) -> str:` 之前）改为：

```python
def run_gates(cfg: dict, worktree: Path, files: list[str], run_dir: Path,
              progress: ProgressReporter) -> str:
```

并在 `for name, command, cwd in checks:` 循环体的第一行插入：

```python
            progress.stage(f"gate_{name}")
```

- [ ] **Step 2: process_feedback 接入阶段与动作**

把 `process_feedback` 中从 `try:` 到 `parsed = invoke_claude(...)` 的这段（含 `log(...)` 下一行起的语句）整体替换为：

```python
    progress = ProgressReporter(api, feedback_id)
    try:
        progress.stage("preparing")
        worktree, branch, base_sha = prepare_worktree(cfg, feedback)
        if feedback.get("attachments"):
            progress.stage("fetching")
        attachments = download_attachments(api, feedback, run_dir)
        prompt = build_prompt(feedback, attachments)
        (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")

        progress.stage("agent")
        parsed = invoke_claude(cfg, worktree, prompt, run_dir, on_action=progress.action)
```

把 `run_gates` 调用改为：

```python
        gate_summary = run_gates(cfg, worktree, files, run_dir, progress)
```

把 `commit_changes` 调用之前插入：

```python
        progress.stage("committing")
        commit_stat = commit_changes(worktree, feedback, base_sha)
```

- [ ] **Step 3: 语法校验**

Run（在 `scripts/ai-feedback-runner/` 下）：

```powershell
D:\software\miniconda3\python.exe -m py_compile runner.py
```

Expected: 无输出。注意：旧 runner（PID 22592）持有 `.runner.lock`，本 Task 不要尝试启动 runner 实测，实测放 Phase D。

- [ ] **Step 4: Commit**

```powershell
git add scripts/ai-feedback-runner/runner.py
git commit -m "feat(ai-runner): process_feedback/run_gates 按阶段上报进度"
```

---

## Phase C：前端

### Task C1: 阶段元数据、抽屉快照同步、耗时与自动滚动

**Files:**
- Modify: `frontend/src/pages/BasicDataCenter/FeedbackManagement/index.tsx`

**Interfaces:**
- Produces: `aiStageMeta` 与 `stageEntries` / `actionEntries` / `fmtClock` / `elapsedMinutes` 辅助函数，供 Task C2 的 JSX 使用；抽屉随 15s 轮询同步。

- [ ] **Step 1: 加阶段元数据与辅助函数**

在 `aiStatusMeta` 定义之后插入：

```ts
const aiStageMeta: Record<string, { label: string }> = {
  preparing: { label: '准备隔离环境' },
  fetching: { label: '下载附件' },
  agent: { label: 'AI 修改代码' },
  gate_backend: { label: '后端测试' },
  gate_frontend: { label: '前端构建' },
  committing: { label: '提交代码' },
}

const stageEntries = (list?: any[]) => (list || []).filter((e: any) => e?.kind === 'stage')
const actionEntries = (list?: any[]) => (list || []).filter((e: any) => e?.kind === 'action')
const fmtClock = (t?: string | null) => (t ? dayjs(t).format('HH:mm:ss') : '')
const elapsedMinutes = (from?: string | null) => {
  if (!from) return 0
  return Math.max(0, dayjs().diff(dayjs(from), 'minute'))
}
```

- [ ] **Step 2: 加 ref 与 tick 状态**

在 `const tableWrapRef = useRef<HTMLDivElement | null>(null)` 之后插入：

```ts
  const actionBoxRef = useRef<HTMLDivElement | null>(null)
  const [, setProgressTick] = useState(0)
```

- [ ] **Step 3: fetchData 同步抽屉快照**

把 `fetchData` 中的

```ts
      setData(res.data?.items || [])
```

替换为：

```ts
      const items = res.data?.items || []
      setData(items)
      setDetail((prev: any) => (prev ? items.find((i: any) => i.id === prev.id) || prev : prev))
```

- [ ] **Step 4: 加耗时 ticker 与自动滚动 effect**

在「AI 任务进行中时每 15s 自动刷新」useEffect 之后插入：

```ts
  // AI 执行中：当前阶段耗时每 30s 重算
  useEffect(() => {
    if (detail?.ai_status !== 'running') return
    const timer = setInterval(() => setProgressTick(t => t + 1), 30000)
    return () => clearInterval(timer)
  }, [detail?.ai_status, detail?.ai_stage]) // eslint-disable-line react-hooks/exhaustive-deps

  // 动作列表更新时自动滚到底部
  useEffect(() => {
    const el = actionBoxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [detail?.ai_progress?.length, detail?.ai_stage])
```

- [ ] **Step 5: Commit（构建验证在 C2 一起做）**

```powershell
git add frontend/src/pages/BasicDataCenter/FeedbackManagement/index.tsx
git commit -m "feat(feedback): 抽屉进度快照同步 + 阶段耗时 ticker"
```

---

### Task C2: 抽屉阶段时间轴与动作列表

**Files:**
- Modify: `frontend/src/pages/BasicDataCenter/FeedbackManagement/index.tsx`

**Interfaces:**
- Consumes: `aiStageMeta` / 辅助函数（C1）、后端 `ai_progress` / `ai_stage` / `ai_stage_started_at`（A1-A3）。
- Produces: 抽屉「AI 实现」区块内的执行进度时间轴 + 最近动作列表。

- [ ] **Step 1: 插入进度区块**

在抽屉「AI 实现」区块中，把

```tsx
                  {canHandle && aiAction(detail)}
                </div>
                {detail.ai_note && (
```

替换为：

```tsx
                  {canHandle && aiAction(detail)}
                </div>
                {detail.ai_progress?.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 'calc(12px * var(--font-size-scale))', color: '#94a3b8', fontWeight: 600, letterSpacing: '0.05em', marginBottom: 8 }}>
                      执行进度
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {stageEntries(detail.ai_progress).map((e: any, i: number, arr: any[]) => {
                        const isCurrent = detail.ai_status === 'running' && detail.ai_stage === e.stage
                        const next = arr[i + 1]
                        const duration = next ? dayjs(next.at).diff(dayjs(e.at), 'minute') : null
                        return (
                          <div key={`stage-${i}-${e.stage}`} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{
                              width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                              background: isCurrent ? '#5b5bd6' : '#cbd5e1',
                              boxShadow: isCurrent ? '0 0 0 3px rgba(91,91,214,.15)' : undefined,
                            }} />
                            <span style={{ fontSize: 'calc(12.5px * var(--font-size-scale))', color: isCurrent ? '#0f172a' : '#64748b', fontWeight: isCurrent ? 600 : 400 }}>
                              {aiStageMeta[e.stage]?.label || e.text || e.stage}
                            </span>
                            <span className="sc-note">{fmtClock(e.at)}</span>
                            {isCurrent
                              ? <span className="sc-note">已运行 {elapsedMinutes(detail.ai_stage_started_at)} 分钟</span>
                              : duration !== null && <span className="sc-note">耗时 {duration} 分钟</span>}
                          </div>
                        )
                      })}
                    </div>
                    {actionEntries(detail.ai_progress).length > 0 && (
                      <>
                        <div style={{ fontSize: 'calc(12px * var(--font-size-scale))', color: '#94a3b8', fontWeight: 600, letterSpacing: '0.05em', margin: '10px 0 6px' }}>
                          最近动作
                        </div>
                        <div ref={actionBoxRef} style={{ maxHeight: 160, overflow: 'auto', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '6px 10px' }}>
                          {actionEntries(detail.ai_progress).map((e: any, i: number) => (
                            <div key={`action-${i}`} className="sc-note" style={{ lineHeight: 1.9, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              <span className="sc-mono" style={{ marginRight: 6 }}>{fmtClock(e.at)}</span>
                              {e.text}
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}
                {detail.ai_note && (
```

- [ ] **Step 2: 构建验证**

Run（在 `frontend/` 下）：

```powershell
npm run build
```

Expected: `tsc -b && vite build` 成功，无 TS 错误。

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/pages/BasicDataCenter/FeedbackManagement/index.tsx
git commit -m "feat(feedback): 详情抽屉阶段时间轴与最近动作列表"
```

---

## Phase D：端到端验证（需用户确认后执行）

### Task D1: 重启 runner 并实测进度可见

**Files:** 无代码改动。

**步骤（执行前先向用户确认，用户也可自行操作）：**

- [ ] **Step 1: 确认后端已加载新代码**

开发后端（`http://192.168.0.178:8000`）若为 `--reload` 会自动加载；确认 `init_database.py` 已跑过（A1 Step 3）。

- [ ] **Step 2: 停旧 runner 并清锁**

```powershell
Stop-Process -Id 22592 -Force   # 实际 PID 以 .runner.lock 内容为准
Remove-Item scripts\ai-feedback-runner\.runner.lock -ErrorAction SilentlyContinue
```

- [ ] **Step 3: 启动新 runner**

```powershell
Start-Process -FilePath "D:\software\miniconda3\python.exe" -ArgumentList "runner.py" -WorkingDirectory "D:\wanghuazheng\project\SPC-v2\scripts\ai-feedback-runner" -WindowStyle Minimized
```

（或用户在自有控制台重启，效果相同。）

- [ ] **Step 4: 实测**

1. 在反馈管理页派一条真实反馈给 AI；
2. 打开详情抽屉：观察「执行进度」阶段推进（preparing → fetching/agent → gate_* → committing）、「最近动作」滚动、当前阶段「已运行 X 分钟」；
3. 15 秒内列表轮询应把新进度带进抽屉；
4. 完成后（done/failed）确认：进度历史仍可查看、`ai_note` 摘要正常、当前阶段高亮消失。

Expected: 全流程可见；若 runner 日志出现「进度上报失败（不影响任务）」，任务仍正常完成（降级符合预期）。
