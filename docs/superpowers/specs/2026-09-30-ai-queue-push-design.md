# 问题反馈派单即时送达 Runner（长轮询推送）设计方案

- 日期：2026-09-30
- 状态：已评审通过（待落实现计划）
- 涉及模块：问题反馈（basicdata.feedback）+ 本地 Runner（scripts/ai-feedback-runner）
- 前置：`2026-09-29-feedback-ai-autofix-design.md`（AI 自动实现）、`2026-09-30-feedback-ai-progress-design.md`（进度可视化）

## 1. 背景与目标

现状：runner 每 `poll_interval_seconds`（默认 10，本机 5 秒）轮询 `GET /feedback?ai_status=queued`。派单到认领存在最长一个轮询周期的延迟，且"点击是否送达"不可感知。

目标：派单（新派 + 重排）后，后端**主动、即时**把任务送达正在等待的 runner——runner 从"定时来问"改为"挂着等"，后端派单时立即唤醒。

成功标准：

1. 点击「交 AI 实现」到 runner 认领（`queued → running`）延迟 < 1 秒。
2. 等待期间不占用数据库连接、不阻塞其他请求；后端重启/网络断开时 runner 自动重连继续等待，任务不丢（DB 为事实来源）。
3. 保留退避重试：等待接口异常时按 `poll_interval_seconds` 退避后重连。

## 2. 术语

| 术语 | 含义 |
|---|---|
| 长轮询 | GET 请求挂起最长 `timeout_seconds`；有任务立即返回、无任务超时返回空 |
| 等待者 | 正在 `ai-queue-wait` 上挂起的 runner 请求 |
| 唤醒 | 派单事务提交后 set 所有等待者事件，使挂起请求立即复查并返回 |

## 3. 后端设计

### 3.1 新端点

`GET /api/v1/basicdata/feedback/ai-queue-wait`

- 参数：`timeout_seconds: float = Query(20, ge=1, le=30)`；
- 权限：`_can_handle`（runner 账号），失败 403；
- 语义：
  1. 立即查 `ai_status = "queued"`，按 `created_at` 升序取最多 10 条 id；有则直接返回；
  2. 无则挂起等待，被唤醒或超时后重复第 1 步；直到出现任务或超时返回空。
- 响应：`ResponseModel[dict]`，`data = {"ids": [反馈 id...]}`。

### 3.2 等待与唤醒机制

- 模块级等待者集合：`_queue_waiters: set[asyncio.Event]`；
- `notify_queue_waiters()`：遍历集合逐个 `set()`（不阻塞、异常不影响调用方）；
- 等待循环：

```
event = asyncio.Event()
_queue_waiters.add(event)          # 先注册再查库，消除唤醒丢失竞态
try:
    deadline = time.monotonic() + timeout_seconds
    while True:
        ids = 查询 queued id 列表（limit 10）
        await db.rollback()        # 只读事务结束，归还连接
        if ids: return ids
        remaining = deadline - time.monotonic()
        if remaining <= 0: return []
        try: await asyncio.wait_for(event.wait(), timeout=min(1.0, remaining))
        except asyncio.TimeoutError: pass
        event.clear()
finally:
    _queue_waiters.discard(event)
```

- 即时路径：`ai-queue` 提交后调用 `notify_queue_waiters()`，等待者毫秒级复查返回；
- 兜底路径：1 秒周期复查，覆盖多 worker / 未来多进程部署，最差退化到 ≤1 秒延迟；
- 生产与开发 compose 均为单进程 uvicorn（已确认命令无 `--workers`），即时路径始终生效。

### 3.3 派单唤醒接入

`ai_queue_feedback` 完成 `commit`/`refresh` 之后调用 `notify_queue_waiters()`。覆盖三条路径：新派单、`running` 重排、`failed` 重试（均经由 ai-queue）。

### 3.4 路由顺序（关键）

端点必须声明在 `GET /{feedback_id}` **之前**。否则 `/{feedback_id}` 会先匹配字符串 `"ai-queue-wait"` 并在 int 转换处报 422，永远不会落到本端点。

### 3.5 资源约束

- 每次空查询后 `await db.rollback()` 释放连接：挂起 20 秒不持有 DB 连接；
- 空闲时每等待者约 1 SELECT/秒（单 runner 场景可忽略）。

## 4. Runner 设计

- `ApiClient.wait_queued(timeout_seconds: int = 20) -> list[int]`：GET `ai-queue-wait`；请求超时取 `timeout_seconds + 10`；`code != 0` 抛 `RuntimeError`；
- 常量 `WAIT_TIMEOUT_SECONDS = 20`；
- 主循环改造：

```
while not STOP["requested"]:
    try:
        ids = api.wait_queued(2 if args.once else WAIT_TIMEOUT_SECONDS)
    except Exception as exc:
        log(f"等待队列失败: {exc}")
        wait_for(cfg["poll_interval_seconds"])   # 退避重连
        continue
    if not ids:
        if args.once: log("队列为空，退出（--once）"); return
        continue                                  # 服务端已等待，直接续等
    for feedback_id in ids:
        if STOP["requested"]: break
        claimed = api.claim(feedback_id)（409 跳过）
        process_feedback(...)
```

- 删除不再使用的 `list_queued`（保持无死代码）；
- `poll_interval_seconds` 语义变为"等待出错后的退避间隔"，配置键与默认值不变（不动用户 `config.local.json`）；
- Ctrl+C：空闲挂起最长 20 秒后退出，可接受（不为此引入可中断 HTTP 机制）。

## 5. 前端

无改动。派单流程与 UI 不变，仅 runner 开始更快；进度可视化沿用既有链路。

## 6. 测试（backend/tests/integration/test_feedback_ai_api.py 追加）

1. `test_ai_queue_wait_returns_existing`：已有 queued 任务时请求立即返回该 id；
2. `test_ai_queue_wait_wakes_on_dispatch`：以 `timeout_seconds=5` 发起 wait（asyncio task），0.2s 后派单 → wait 立即返回 id，且完成耗时显著小于超时（证明是唤醒而非超时兜底）；
3. `test_ai_queue_wait_timeout_returns_empty`：无任务、`timeout_seconds=1` → 返回空 ids；
4. `test_ai_queue_wait_requires_handle_permission`：无处理权限 → 403；
5. 全量回归 `python -m pytest`。

## 7. 非目标（YAGNI）

- 不做 runner 心跳/在线状态展示、`running` 超时自动回退排队（另行评估）；
- 不加 SSE / WebSocket / Redis pub-sub / 新依赖；
- 不改数据库 schema（无迁移）、不改前端。

## 8. 交付物清单

| 文件 | 改动 |
|---|---|
| `backend/app/api/v1/basicdata/feedback.py` | `ai-queue-wait` 端点 + 等待者集合/唤醒函数 + `ai_queue_feedback` 唤醒调用 |
| `backend/tests/integration/test_feedback_ai_api.py` | 4 个长轮询用例 |
| `scripts/ai-feedback-runner/runner.py` | `ApiClient.wait_queued` + 主循环改造 + 删除 `list_queued` |

## 9. 验证方式

1. 后端：`cd backend && python -m pytest tests/integration/test_feedback_ai_api.py -v` + 全量。
2. Runner：`python -m py_compile runner.py`。
3. 端到端：重建 backend 镜像 → 重启 runner（新代码）→ 重排 #118 → 实测 `POST ai-queue` 到 `ai_status=running` 的延迟（预期 <1s）→ #118 继续跑完。
4. 断线演练（可选）：停/启 backend 容器，runner 日志出现等待失败退避后自动恢复等待，任务不丢。

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 长轮询连接被中间层超时断开 | runner 直连后端端口（生产 18085，无 nginx）；单请求 ≤30s；异常退避重连 |
| asyncio.Event 唤醒丢失 | 先注册再查库消除竞态；1 秒周期复查兜底 |
| 未来多 worker 部署 | 即时路径失效，退化为 ≤1 秒等待，功能不失效 |
| Ctrl+C 响应变慢 | 空闲最长 20 秒退出；文档说明即可 |
