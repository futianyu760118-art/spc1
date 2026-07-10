# AI 智能助手稳固性改造 — 设计稿

**日期**: 2026-07-10
**范围**: 在不破坏现有架构的前提下，引入 Mini-Agent 的稳健性最佳实践

---

## 1. 改造目标

| 目标 | 现状 | 目标 |
|---|---|---|
| 长会话不丢信息 | 20 条滑动窗口截断 | 80k token 阈值自动摘要 |
| LLM/工具调用稳定 | 1 次重试 + 固定 0.5s 延迟 | 指数退避 + 异常类型分类 |
| 思考过程可观测 | 直接剥除丢弃 | 透传 `event:thinking` 给前端 |
| 取消/中断 | 无法取消 | 客户端断连 + 后端超时自动取消 |
| 调试可观测 | 标准 logging | JSONL 文件 + 查询接口 |
| 工具基类 | `dataclass ToolDef` | 沿用不动（增量集成） |

---

## 2. 模块新增/变更

### 2.1 新增文件

```
backend/app/services/assistant/
├── context_manager.py        # 上下文摘要与 token 估算
├── retry.py                  # 异步重试装饰器（指数退避）
├── run_logger.py             # JSONL 结构化 Agent 日志
└── cancellation.py           # 取消事件管理
```

### 2.2 修改文件

- `app/services/ai/dashscope_provider.py`：在 `chat` / `chat_with_tools` 返回值中暴露 `usage.total_tokens`
- `app/services/ai/openai_provider.py`：同上
- `app/services/ai/base.py`：`ChatWithToolsResult` 增加 `usage` 字段
- `app/services/assistant/agent.py`：接入 context_manager + retry + run_logger + cancellation
- `app/services/assistant/agent_stream.py`：SSE 新增 `event:thinking` 事件
- `app/services/assistant/session_store.py`：摘要后的新结构正确序列化
- `app/api/v1/assistant/routes.py`：新增 `GET /assistant/logs/{trace_id}` 接口
- `app/core/config.py`：新增 4 个 `AI_*` 配置项
- `app/schemas/assistant/schemas.py`：`AssistantReply` 新增可选 `thinking` 字段

---

## 3. 关键设计

### 3.1 上下文管理（context_manager.py）

**触发条件**（同时满足任一）：
- 本地 tiktoken 估算 > 80000
- LLM API 上报 `usage.total_tokens` > 80000

**摘要策略**（沿用 Mini-Agent `system + user + summary` 结构）：
```
原：[system, u1, a1, t1, a2, t2, u2, a3, t3, u3, a4]  (高 token)
新：[system, u1, summary_1, u2, summary_2, u3, ...]   (低 token)
```
- 保留 system prompt
- 保留所有 user 消息（用户意图不能丢）
- 摘要区间：每个 user 后的 assistant/tool 执行过程

**配置开关**：
```python
AI_SUMMARY_ENABLED = True        # 默认启用
AI_SUMMARY_TOKEN_LIMIT = 80000   # 阈值
```

**失败兜底**：摘要 LLM 调用失败时，回退到滑动窗口截断（保留最近 6 条），不阻断主流程。

### 3.2 重试（retry.py）

参考 Mini-Agent `RetryConfig`：

```python
@async_retry(RetryConfig(
    max_retries=3,
    initial_delay=1.0,
    exponential_base=2.0,
    max_delay=30.0,
    retryable_exceptions=(asyncio.TimeoutError, ConnectionError, ...),
))
async def _call_llm(...): ...
```

**应用范围**：LLM 调用、tool 执行、摘要调用。
**不重试**：业务校验错误、权限错误、Pydantic 校验错误。

### 3.3 Thinking 透传（agent_stream.py）

**SSE 事件新增**：
```
event: thinking
data: {"text": "正在分析订单风险...", "stage": "intent|tool_select|reasoning"}
```

**ThinkTagFilter 现有逻辑调整**：
- 现状：剥除 think 块丢弃
- 目标：累积到 `thinking_chunks`，作为 SSE `thinking` 事件分批推送；最终输出文本仍剥离 think 块

**新增终态事件**：
```
event: cancelled
data: {"reason": "client_disconnected|timeout", "round": 2}
```

### 3.4 取消机制（cancellation.py）

```python
class CancellationRegistry:
    _events: dict[session_id, asyncio.Event] = {}

    @classmethod
    def get_or_create(cls, session_id) -> asyncio.Event: ...
    @classmethod
    def trigger(cls, session_id, reason: str): ...
    @classmethod
    def cleanup(cls, session_id): ...
```

**触发点**：
- SSE 流式响应中，FastAPI 客户端断连 → `Request.is_disconnected()` 检测 → trigger
- 工具调用总时长超过 120s → trigger
- Agent 循环每个 round 起点检查 `_check_cancelled()`，触发后清理未完成消息

**取消粒度**：仅在 step/round 边界触发，避免半轮消息残留。

### 3.5 结构化日志（run_logger.py）

**存储路径**：`backend/logs/assistant/{YYYY-MM-DD}/{trace_id}.jsonl`

**每行结构**：
```json
{"ts": "2026-07-10T10:30:00.123Z", "trace_id": "...", "session_id": "...",
 "user_id": "...", "event": "request|response|tool_call|tool_result|summary|error|cancel",
 "data": {...}}
```

**新增 API**：
- `GET /api/v1/assistant/logs/{trace_id}` → 返回完整 JSONL
- `GET /api/v1/assistant/logs?session_id=xxx&date=2026-07-10` → 列表

**写入策略**：异步写入（`asyncio.create_task`）+ 日志目录按天切分 + 30 天保留（可配置）。

### 3.6 工具层

**不变**。保留 `tool_registry.py` 的 `ToolDef` dataclass 与现有 14 个工具。

---

## 4. 数据流变更

### 4.1 chat（非流）流程

```
用户 → API → agent.run()
  ├─ 加载历史
  ├─ 估算 token → 触发摘要
  ├─ 意图识别（带 retry）
  ├─ 工具调用循环（带 retry + cancellation check）
  └─ 输出 AssistantReply（含 thinking 字段）
```

### 4.2 chat/stream 流程

```
用户 → API → agent_stream.run_stream()
  ├─ event: session     （session_id, trace_id）
  ├─ event: thinking    （stage=intent, message=...）
  ├─ event: thinking    （stage=reasoning, text=...）   ← NEW
  ├─ event: tool_start
  ├─ event: tool_done
  ├─ event: delta       （最终正文，不含 think）
  ├─ event: cards
  ├─ event: cancelled   （仅取消时）                   ← NEW
  └─ event: done
```

---

## 5. 兼容性

| 维度 | 处理 |
|---|---|
| API 路由 | 全部保留，新增 2 个 logs 接口 |
| AssistantReply schema | 新增 `thinking: str \| None` 字段（可选，向后兼容） |
| 现有 14 个 tool | 不动 |
| 现有 ai provider | 在 `ChatWithToolsResult` 上补 `usage` 字段（向前兼容） |
| 前端 | assistant_stream 已支持新 event 类型，按需添加 thinking 渲染 |
| 数据库 | 不涉及 schema 变更 |
| .env | 新增 4 个 AI_* 配置项，默认值兼容现有行为 |

---

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 摘要 LLM 调用失败导致回复中断 | 失败时回退到滑动窗口截断，不阻断主流程 |
| 取消时机不当导致消息不一致 | 严格只在 step 边界（round start/end）检查 |
| tiktoken 模型偏差 | 优先用 API 上报 token，估算仅作触发辅助 |
| JSONL 日志膨胀 | 按天切分目录，30 天清理（可配置），加异步写入 |
| 重试风暴 | 指数退避 + max_delay=30s 上限 + 总耗时控制 |
| 取消后无响应 | SSE 立即发 `event:cancelled` 后断开 |

---

## 7. 测试策略

- 单元测试：`tests/test_retry.py` / `test_context_manager.py` / `test_run_logger.py` / `test_cancellation.py`
- 回归测试：4 类典型对话（查订单/查齐套/今日简报/通用聊天）
- 长会话压测：构造 20+ 轮 tool 调用，验证摘要触发
- 取消压测：SSE 客户端断连 → 验证 5s 内 agent 停止
