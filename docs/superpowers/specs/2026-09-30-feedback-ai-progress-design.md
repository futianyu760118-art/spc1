# 问题反馈 AI 实现过程可视化（进度上报）设计方案

- 日期：2026-09-30
- 状态：已评审通过（待落实现计划）
- 涉及模块：问题反馈（basicdata.feedback）+ 本地 Runner（scripts/ai-feedback-runner）
- 前置：`docs/superpowers/specs/2026-09-29-feedback-ai-autofix-design.md`（AI 自动实现已上线）

## 1. 背景与目标

现状：处理人「交 AI 实现」后，反馈在 `ai_status = queued / running` 期间，管理页只有一个「实现中」标签。runner 在开发机依次执行 worktree 创建、附件下载、claude 改码、后端 pytest、前端 build、提交，全程最长 60 分钟，界面上无法区分"正在写代码"、"正在跑测试"、"卡住了"。

目标：把 AI 实现过程做成可见的**阶段时间轴 + 实时动作流**：

1. `running` 期间，反馈详情抽屉展示：当前阶段、阶段耗时、最近动作（如「修改 frontend/src/xxx.tsx」），随现有列表自动刷新节奏更新；
2. 动作由 runner 流式解析 claude 输出生成；解析异常时自动退化为仅阶段，不报错；
3. 进度上报对 runner 是**纯尽力行为**：网络失败、后端不可用、接口缺失都只记本地日志，绝不影响任务本身。

成功标准：

1. 派单后打开抽屉，≤15 秒内能看到阶段推进与动作滚动，不再只有一个「实现中」。
2. 阶段至少覆盖：准备环境 →（下载附件）→ AI 修改代码 → 后端测试 / 前端构建 → 提交。
3. 断网 / 旧后端场景下，runner 任务照常完成，界面自动退化为现状（无报错、无脏数据）。
4. 完成后（done/failed）进度历史仍可查看，与 `ai_note` 摘要互相印证。

## 2. 术语

| 术语 | 含义 |
|---|---|
| 阶段（stage） | runner 执行流程中人工可读的里程碑，白名单枚举，顺序固定 |
| 动作（action） | claude 执行中产生的细粒度事件，由 `tool_use` 转写为中文短句 |
| 进度快照 | 反馈行上的 `ai_stage` / `ai_stage_started_at` / `ai_progress` 三列 |
| stream-json | claude CLI `-p --output-format stream-json` 的逐行 JSON 事件流 |

## 3. 数据模型（方案 A：行内快照）

按仓库约定：SQLAlchemy model 与 `backend/init_database.py` 的 `migrate_columns["feedback"]` **同时登记**。

### 3.1 `feedback` 表新增列

| 列 | 类型 | 说明 |
|---|---|---|
| `ai_stage` | varchar(32) NULL | 当前阶段 key（白名单见 3.2）；`ai-finish` 时置 NULL |
| `ai_stage_started_at` | timestamp NULL | 当前阶段开始时间，前端据此显示「已运行 X 分钟」 |
| `ai_progress` | JSONB NULL | 执行记录数组，只保留最近 50 条 |

`ai_progress` 元素结构：

```json
{ "at": "2026-09-30T10:05:00", "kind": "stage", "stage": "agent", "text": "AI 修改代码" }
{ "at": "2026-09-30T10:06:12", "kind": "action", "stage": "agent", "text": "修改 frontend/src/x.tsx" }
```

- `at`：服务端本地时间 ISO8601（`datetime.now().isoformat(timespec="seconds")`，与库内其它时间一致）；
- `kind`：`stage`（阶段切换）或 `action`（动作）；
- `stage`：stage 条目为自身 key；action 条目为发生时所处阶段 key（可为 null）；
- `text`：stage 条目为中文标签；action 条目为动作文案，服务端截断到 200 字符。

### 3.2 阶段白名单（backend 常量，顺序即展示顺序）

| key | 标签 | 触发点 |
|---|---|---|
| `preparing` | 准备隔离环境 | 认领后、创建 worktree 前 |
| `fetching` | 下载附件 | 有附件时、下载前 |
| `agent` | AI 修改代码 | 调用 claude 前 |
| `gate_backend` | 后端测试 | 执行 pytest 前 |
| `gate_frontend` | 前端构建 | 执行 npm build 前 |
| `committing` | 提交代码 | git commit 前 |

只上报实际发生的阶段（无附件则无 `fetching`；仅前端改动则无 `gate_backend`）。

### 3.3 生命周期规则

- `ai-queue`（派单 / 重排）：清空三列，新一轮从零开始；
- `ai-claim`：不动进度列（此时为空）；
- `ai-progress`：仅 `running` 时接受写入；
- `ai-finish`：保留 `ai_progress` 作为历史，`ai_stage` / `ai_stage_started_at` 置 NULL（终态由 `ai_status` 表达）。

## 4. 后端 API

### 4.1 新增端点

`POST /api/v1/basicdata/feedback/{feedback_id}/ai-progress`

请求体 schema（`app/schemas/basicdata/feedback.py`）：

```python
class FeedbackAiProgress(BaseModel):
    stage: Optional[str] = None          # 阶段 key，白名单校验
    actions: Optional[List[str]] = None  # 动作批，单次最多 20 条
```

校验与副作用（要求现有「处理问题反馈」权限，复用 `_can_handle`）：

1. `_can_handle` 不通过 → 403；
2. 反馈不存在 → 404；
3. `with_for_update()` 行锁；`ai_status != "running"` → 409（陈旧上报自然被丢弃）；
4. `actions` 逐条 `strip`，丢弃空串，截断至 200 字符，最多取前 20 条；处理完后 stage 与 actions 均无有效内容 → 400；`stage` 不在白名单 → 400；
6. 生效顺序：先 stage 条目（同时更新 `ai_stage` / `ai_stage_started_at = now()`），再追加 action 条目（带当前 `ai_stage` 作为 `stage`）；
7. `ai_progress = (旧数组 + 新条目)[-50:]` —— **必须整体赋值**（SQLAlchemy JSONB 不追踪原地 append）；
8. 手动 `commit` + `refresh`（沿用本模块既有写法）。

响应：`ResponseModel[dict]`，`data = {"ai_status": ..., "ai_stage": ...}`（进度回写无需返回全量 FeedbackOut）。

### 4.2 既有端点调整

- `ai_queue_feedback`：置 `queued` 时同时 `ai_progress = None; ai_stage = None; ai_stage_started_at = None`（覆盖失败重试与 running 重排两种路径）；
- `ai_finish_feedback`：保留 `ai_progress`，置 `ai_stage = None; ai_stage_started_at = None`；
- `FeedbackOut` 追加输出字段 `ai_stage` / `ai_stage_started_at` / `ai_progress`（列表与详情自动携带）。

## 5. Runner 改造（scripts/ai-feedback-runner/runner.py）

### 5.1 上报客户端

`ApiClient` 新增：

```python
def progress(self, feedback_id, stage=None, actions=None) -> None
```

`POST /{id}/ai-progress`，body 仅含非空字段；`code != 0` 抛 `RuntimeError`（由调用方兜底）。

### 5.2 节流上报器

新增 `ProgressReporter`（持有 `api`、`feedback_id`、动作缓冲、上次 flush 时间）：

- `stage(name)`：先 flush 缓冲动作，再上报该阶段（try/except 记日志「进度上报失败（不影响任务）」）；
- `action(text)`：入缓冲；缓冲 ≥20 条或距上次 flush ≥5 秒即 flush；
- `flush()`：批量上报缓冲的动作。

对 `process_feedback` 的调用点：认领后立即 `stage("preparing")`；有附件时 `stage("fetching")`；调用 claude 前 `stage("agent")`；`run_gates` 执行对应门禁前 `stage("gate_backend"/"gate_frontend")`（签名追加 `progress` 参数）；commit 前 `stage("committing")`。

### 5.3 claude 流式调用

`invoke_claude` 改造（签名追加 `on_action` 回调）：

- 命令追加 `--output-format stream-json --verbose`（CLI 2.1.284 已验证；stream-json 与 `--print` 组合要求 `--verbose`），权限参数与工具白名单逻辑不变；
- `subprocess.Popen`：stdout 逐行读取；stderr 重定向到 `run_dir/claude-stderr.txt` 文件句柄（避免管道阻塞）；prompt 写 stdin 后关闭；
- 看门狗：`threading.Timer` 到 `timeout_minutes` 触发杀进程（Windows 优先 `taskkill /F /T /PID`，失败退回 `proc.kill()`），并置超时标记；结束后据此抛 `RunFailure("代理执行超时…")`；
- 逐行处理：
  - 原始行写入 `run_dir/claude-output.txt`（保持现有日志可回溯）；
  - `type == "assistant"`：其 content 中每个 `tool_use` 块经 `describe_tool_use` 转写为中文动作并回调 `on_action`；无法识别的工具输出「使用工具 {name}」；
  - `type == "result"`：记录 `is_error` / `result`，作为最终返回；
  - 其它事件忽略；
- 流结束仍未出现 `result` 事件 → `RunFailure`（沿用"输出无法解析"失败语义，附日志路径）。

`describe_tool_use` 转写规则：

| 工具 | 文案 |
|---|---|
| Read / Write / Edit | 读取 / 新建 / 修改 {file_path} |
| NotebookEdit | 修改 {notebook_path} |
| Grep | 搜索 {pattern} |
| Glob | 查找文件 {pattern} |
| Bash | 执行命令：{command}（截断 120 字符） |
| 其它 | 使用工具 {工具名} |

### 5.4 兼容与降级

- 目标后端无 `ai-progress` 端点（旧版本）→ 404，记本地日志后继续；
- 所有上报包裹 try/except，任何异常不得中断或改变任务结果；
- 旧版 runner（不改造）连新后端：不上报进度，界面维持现状，无报错。

## 6. 前端改动（仅反馈管理页）

`frontend/src/pages/BasicDataCenter/FeedbackManagement/index.tsx`：

1. 新增 `aiStageMeta`（key → 中文标签，与后端白名单一致，沿用现有 statusMeta 的前端重复定义模式）与顺序数组；
2. 抽屉「AI 实现」区块扩展：
   - 有 `ai_progress` 时渲染「执行进度」：按时间顺序的 stage 条目，完成阶段显示耗时（下一阶段起始时间差），当前阶段高亮并显示「已运行 X 分钟」（30s ticker，来源 `ai_stage_started_at`）；`done/failed` 后同一区块静态展示历史；
   - 渲染「最近动作」：action 条目时间顺序排列，限高滚动，更新时自动滚到底部；
   - 无 `ai_progress` 时维持现有展示（状态标签 + 分支 + ai_note）；
3. `fetchData` 成功拿到列表后同步抽屉快照（否则抽屉不会随 15s 轮询刷新）：

```ts
setDetail((prev: any) => prev ? (items.find((i: any) => i.id === prev.id) || prev) : prev)
```

4. 列表页不加新元素；沿用现有「存在 queued/running 时每 15s 自动刷新」；
5. 不新增依赖，样式复用 `sc-tag` / `sc-note` / `DrawerSection` 与行内样式。

## 7. 安全与非功能约束

1. 权限不变：上报端点复用 `_can_handle`，不新增权限点；提交人可见性维持现状（有页面访问权即可看）。
2. 写入有界：单次 ≤20 条、每条 ≤200 字符、总量 50 条，JSONB 不会无界增长。
3. 动作文案由 runner 依据工具名与参数生成，不把反馈原文引入展示链路。
4. 上报失败静默降级，不写脏数据（409/404 直接丢弃）。

## 8. 非目标（YAGNI）

- 不做完整日志在线查看（日志仍落开发机 `runs/<id>-<时间戳>/`）；
- 不做多轮 run 历史表（重排清空旧进度，终态摘要仍在 `ai_note`）；
- 不做 SSE / WebSocket 实时推送（沿用轮询）；
- 不做 runner 并发、自动合入 / 自动部署 / AI 自动关单。

## 9. 交付物清单

| 文件 | 改动 |
|---|---|
| `backend/app/models/basicdata/feedback.py` | 新增 3 列 |
| `backend/init_database.py` | `migrate_columns["feedback"]` 登记 3 列 |
| `backend/app/schemas/basicdata/feedback.py` | `FeedbackAiProgress` + `FeedbackOut` 3 字段 |
| `backend/app/api/v1/basicdata/feedback.py` | `ai-progress` 端点；`ai-queue` / `ai-finish` 清理逻辑 |
| `backend/tests/integration/test_feedback_ai_api.py` | 进度端点集成测试 |
| `scripts/ai-feedback-runner/runner.py` | stream-json 流式解析 + `ProgressReporter` + 看门狗 |
| `frontend/src/pages/BasicDataCenter/FeedbackManagement/index.tsx` | 阶段时间轴 / 动作流 / 抽屉快照同步 |

## 10. 验证方式

1. 后端：`cd backend && python -m pytest`（全量，含新增用例）。
2. 迁移：`python init_database.py` 连续两次幂等无报错。
3. 前端：`cd frontend && npm run build`。
4. 端到端：重启本机 runner（当前 PID 22592 为旧代码）→ 派一条真实反馈 → 抽屉内阶段推进、动作滚动、15s 内可见；done 后进度历史仍可查看。
5. 降级：runner 指向无端点的旧后端时任务照常完成（本地日志出现「进度上报失败」而无失败回写）。

新增集成测试至少覆盖：

- `queued` 状态上报 → 409；`running` 上报 → 200 且三列生效；
- 非法 stage → 400；stage 与 actions 全空 → 400；
- actions 超量裁剪与 200 字符截断；总条目裁剪至 50；
- 无处理权限 → 403；
- 重排清空进度；finish 保留进度、清空当前阶段。

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| claude stream-json 事件格式随版本变化 | 解析失败自动退化为纯阶段；原始流落 `claude-output.txt` 可回溯；CLI 2.1.284 已验证事件结构 |
| 上报增加 DB 写压力 | 节流 5s + runner 串行单任务，写入量可忽略 |
| 旧 runner 进程不上报 | 交付时重启 runner；期间界面维持现状，无报错 |
| JSONB 无界增长 | 服务端裁剪最近 50 条 + 单条 200 字符截断 |
