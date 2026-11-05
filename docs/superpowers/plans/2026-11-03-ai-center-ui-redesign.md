# 智能中心 UI 重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 按靛蓝精致版设计系统重构智能中心四页（我的助手、智能体管理、AI 智能助手），并收敛菜单、路由与权限元数据。

**Architecture:** 复用全站 `.sc-page` 设计系统（按钮/输入/表格/分页/Tabs 已有靛蓝覆盖），新增模块级 `agent-center.css` 与 `assistant.css` 承载页头、卡片目录、团队卡、聊天工作台等独有骨架；页面重写但后端 API 与 SSE 协议零改动，仅更新权限注册与启动迁移。

**Tech Stack:** React 18 + TypeScript + Ant Design 5 + Zustand / Vite / FastAPI + SQLAlchemy + pytest

**设计文档:** `docs/superpowers/specs/2026-11-03-ai-center-ui-redesign-design.md`

## Global Constraints

- 前端唯一校验 `npm run build`；仓库没有 lint/test 脚本，不新增 ESLint/Prettier/测试运行器。
- 后端全量校验 `python -m pytest`；权限改动必须同时更新 `permission_registry.py` 与 `init_database.py` 迁移。
- 成功端点保持 `{ code, message, data }`；本计划不改任何后端 API 响应。
- 所有新样式作用域到 `.ai-center` / `.ai-chat`，不污染全局；AntD 控件样式复用 `.sc-page` 现有覆盖。
- 不新增依赖；不恢复聊天业务卡片；不改 `useAssistantChat` 的 SSE 协议。
- 不保留死代码：删除旧页面、旧 CSS、无用 import、`ac-fs-*` 引用。
- 最小改动：不改 ERP、审批、订单写操作、AEOS 网关、浮球拖拽逻辑。
- 字体尺寸统一用 `calc(Npx * var(--font-size-scale, 1))`；数字列使用 `font-variant-numeric: tabular-nums`。

---

## Task 1: 后端权限与菜单迁移

**Files:**
- Modify `backend/app/core/permission_registry.py`
- Modify `backend/init_database.py`

**Step 1.1** 修改 `permission_registry.py` 的智能体中心声明（约 478–497 行）：

```python
# 智能中心 — 我的助手、智能体管理
declare_permission(
    "ai.agent.self", "智能中心",
    module="agent", actions=["read"], sort_order=15,
)
declare_permission(
    "ai.agent.assistant", "我的助手",
    module="agent", parent_code="ai.agent.self", actions=["read"],
    route_path="/agents", sort_order=1,
)
declare_permission(
    "ai.agent.admin", "智能体管理",
    module="agent", parent_code="ai.agent.self", actions=["read", "update"],
    route_path="/agents/admin", sort_order=2,
)
```

**Step 1.2** 修改 `init_database.py` 的 `migrate_agent_center_permissions`，删除旧 `ai.agent.self.me` / `ai.agent.team` 权限，新增 `ai.agent.assistant`，并把 `ai.agent.admin` 路由回灌（幂等）：

```python
await conn.execute(text(
    "DELETE FROM sys_permission WHERE code IN ("
    "'ai.agent.self.tasks','ai.agent.team.tasks','ai.agent.team.config',"
    "'ai.agent.self.me','ai.agent.team'"
    ")"
))
await conn.execute(text(
    "UPDATE sys_role SET permissions = permissions "
    "- 'ai.agent.self.tasks' - 'ai.agent.team.tasks' - 'ai.agent.team.config' "
    "- 'ai.agent.self.me' - 'ai.agent.team'"
))
await conn.execute(text(
    "UPDATE sys_user SET permissions = permissions "
    "- 'ai.agent.self.tasks' - 'ai.agent.team.tasks' - 'ai.agent.team.config' "
    "- 'ai.agent.self.me' - 'ai.agent.team' "
    "WHERE permissions IS NOT NULL"
))
await conn.execute(text(
    "UPDATE sys_permission SET name = '智能中心' WHERE code = 'ai.agent.self'"
))
await conn.execute(text(
    "INSERT INTO sys_permission "
    "(code, name, module, parent_code, actions, route_path, sort_order, is_active) "
    "VALUES ('ai.agent.assistant', '我的助手', 'agent', 'ai.agent.self', "
    "'[\"read\"]'::jsonb, '/agents', 1, TRUE) "
    "ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, "
    "parent_code = EXCLUDED.parent_code, route_path = EXCLUDED.route_path, "
    "actions = EXCLUDED.actions, sort_order = EXCLUDED.sort_order, is_active = TRUE"
))
await conn.execute(text(
    "UPDATE sys_permission SET name = '智能体管理', parent_code = 'ai.agent.self', "
    "route_path = '/agents/admin', sort_order = 2 "
    "WHERE code = 'ai.agent.admin'"
))
```

**Step 1.3** 验证：

```bash
cd backend
python -m pytest tests/integration -q
```

Expected: 现有 integration 套件通过（至少无新增失败）。

---

## Task 2: 前端路由与菜单映射

**Files:**
- Modify `frontend/src/router/contentRoutes.tsx`
- Modify `frontend/src/layouts/MainLayout.tsx`

**Step 2.1** `contentRoutes.tsx`：

```tsx
import MyAssistant from '../pages/AgentCenter/MyAssistant'
import AgentAdmin from '../pages/AgentCenter/Admin'
```

删除 `AgentMyAgent`、`AgentTeamConfig` import；路由改为：

```tsx
<Route path="/agents" element={<MyAssistant/>}/>
<Route path="/agents/admin" element={<AgentAdmin/>}/>
```

删除 `/agents/me`、`/agents/team` 两行。

**Step 2.2** `MainLayout.tsx` 的 `getRequiredPermission`（约 613–623 行）：

```ts
if (pathname === '/agents' || pathname === '/agents/') return 'ai.agent.assistant'
if (pathname.startsWith('/agents/admin')) return 'ai.agent.admin'
if (pathname.startsWith('/agents')) return 'ai.agent.self'
```

删除 `if (pathname.startsWith('/agents/team')) return 'ai.agent.team'`。

**Step 2.3** 全局残留检查：

```bash
rg "agents/me|agents/team|ai\.agent\.team|ai\.agent\.self\.me" frontend/src
```

Expected: 仅剩后端 API 调用路径 `/agents/me/team` 等（属于 `services/agent.ts`），无页面/路由引用。

---

## Task 3: 设计系统与共享组件

**Files:**
- Create `frontend/src/pages/AgentCenter/agent-center.css`
- Create `frontend/src/components/Agent/PageHeader.tsx`
- Create `frontend/src/components/Agent/StatCard.tsx`
- Modify `frontend/src/components/Agent/CapabilityTags.tsx`

**Step 3.1** 新建 `agent-center.css`，至少包含：

```css
.ai-center {
  --ai-brand: #5b5bd6;
  --ai-brand-hover: #4c4dc2;
  --ai-brand-soft: #eef0fe;
  --ai-brand-line: #c6cbfa;
  --ai-ink: #0f172a;
  --ai-text: #475569;
  --ai-muted: #94a3b8;
  --ai-border: #e2e8f0;
  --ai-surface: #fff;
  --ai-radius: 10px;
  --ai-shadow: 0 1px 2px rgba(15, 23, 42, .04);
  --ai-shadow-md: 0 4px 12px rgba(15, 23, 42, .08);
  color: var(--ai-ink);
  font-size: calc(13.5px * var(--font-size-scale, 1));
}
.ai-center *, .ai-chat * { box-sizing: border-box; }

.ai-page { display: flex; flex-direction: column; gap: 12px; min-height: 100%; }
.ai-page-head { display: flex; align-items: flex-start; gap: 16px; }
.ai-page-head h1 {
  margin: 0; font-size: calc(20px * var(--font-size-scale, 1));
  font-weight: 650; letter-spacing: -.01em;
}
.ai-page-head p {
  margin: 4px 0 0; font-size: calc(12px * var(--font-size-scale, 1));
  color: var(--ai-muted);
}
.ai-page-head .ai-actions { margin-left: auto; display: flex; gap: 8px; }

.ai-card {
  background: var(--ai-surface); border: 1px solid var(--ai-border);
  border-radius: var(--ai-radius); box-shadow: var(--ai-shadow);
}
.ai-card-head {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-bottom: 1px solid #f1f5f9;
}
.ai-card-head h3 { margin: 0; font-size: calc(14px * var(--font-size-scale, 1)); font-weight: 600; }
.ai-card-head .ai-hint { font-size: calc(12px * var(--font-size-scale, 1)); color: var(--ai-muted); }
.ai-card-head .ai-more { margin-left: auto; }
.ai-card-body { padding: 16px; }

.ai-stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.ai-two-col { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; align-items: start; }
.ai-two-col.reverse { grid-template-columns: 1fr 2fr; }
.ai-tag-list { display: flex; flex-wrap: wrap; gap: 4px; }
.ai-muted { color: var(--ai-muted); font-size: calc(12px * var(--font-size-scale, 1)); }

.ai-team-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.ai-member {
  display: flex; gap: 10px; padding: 12px; border: 1px solid var(--ai-border);
  border-radius: 9px; background: #fff; transition: border-color .12s;
}
.ai-member:hover { border-color: var(--ai-brand-line); }
.ai-avatar {
  width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #7a7de6, #5b5bd6);
  color: #fff; font-weight: 600;
}
.ai-member-main { min-width: 0; flex: 1; }
.ai-member-name { font-weight: 600; color: var(--ai-ink); }
.ai-member-meta { font-size: calc(11.5px * var(--font-size-scale, 1)); color: var(--ai-muted); }

.ai-agent-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.ai-agent-card {
  display: flex; flex-direction: column; gap: 10px; padding: 16px;
  background: #fff; border: 1px solid var(--ai-border); border-radius: 10px;
  box-shadow: var(--ai-shadow); transition: border-color .12s, box-shadow .12s;
}
.ai-agent-card:hover { border-color: var(--ai-brand-line); box-shadow: var(--ai-shadow-md); }
.ai-agent-top { display: flex; align-items: center; gap: 10px; }
.ai-agent-name { font-weight: 600; color: var(--ai-ink); }
.ai-agent-no { font-size: calc(11.5px * var(--font-size-scale, 1)); color: var(--ai-muted); font-variant-numeric: tabular-nums; }
.ai-agent-desc {
  font-size: calc(12.5px * var(--font-size-scale, 1)); color: var(--ai-text);
  line-height: 1.6; min-height: 40px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.ai-agent-foot {
  margin-top: auto; padding-top: 10px; border-top: 1px solid #f1f5f9;
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: calc(12px * var(--font-size-scale, 1)); color: var(--ai-muted);
}
.ai-agent-foot .ai-more { margin-left: auto; display: flex; gap: 4px; }

.ai-empty { padding: 40px 16px; text-align: center; color: var(--ai-muted); }

@media (max-width: 1200px) {
  .ai-agent-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 960px) {
  .ai-stat-grid, .ai-two-col, .ai-two-col.reverse { grid-template-columns: 1fr; }
  .ai-team-grid, .ai-agent-grid { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .ai-agent-card, .ai-member { transition: none; }
}
```

**Step 3.2** `PageHeader.tsx`：

```tsx
import React from 'react'

interface Props {
  title: string
  subtitle?: string
  extra?: React.ReactNode
}

export default function PageHeader({ title, subtitle, extra }: Props) {
  return (
    <div className="ai-page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {extra && <div className="ai-actions">{extra}</div>}
    </div>
  )
}
```

**Step 3.3** `StatCard.tsx`：

```tsx
import React from 'react'

interface Props {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  unit?: string
  accent?: string
  accentBg?: string
  delta?: React.ReactNode
}

export default function StatCard({
  icon, label, value, unit, accent = '#5b5bd6', accentBg = '#eef0fe', delta,
}: Props) {
  return (
    <div
      className="sc-stat-card"
      style={{ ['--accent' as any]: accent, ['--accent-bg' as any]: accentBg }}
    >
      <div className="sc-stat-icon">{icon}</div>
      <div style={{ minWidth: 0 }}>
        <div className="sc-stat-label">{label}</div>
        <div className="sc-stat-value">{value}{unit && <small>{unit}</small>}</div>
        {delta}
      </div>
    </div>
  )
}
```

**Step 3.4** `CapabilityTags.tsx` 改用设计系统标签：

```tsx
import React from 'react'
import { AgentCapabilityItem } from '../../services/agent'

interface CapabilityTagsProps {
  items?: AgentCapabilityItem[] | null
  max?: number
  emptyText?: string
}

export function CapabilityTags({ items, max = 3, emptyText = '未配置能力' }: CapabilityTagsProps) {
  const list = items || []
  return (
    <span className="ai-tag-list">
      {list.slice(0, max).map(item => (
        <span key={item.code} className="sc-tag sc-tag-plain">{item.name}</span>
      ))}
      {list.length > max && <span className="sc-tag sc-tag-plain">+{list.length - max}</span>}
      {list.length === 0 && <span className="ai-muted">{emptyText}</span>}
    </span>
  )
}
```

**Step 3.5** 验证：`cd frontend && npm run build`（此时旧页面仍在，应能编译）。

---

## Task 4: 我的助手页

**Files:**
- Create `frontend/src/pages/AgentCenter/MyAssistant/index.tsx`
- Create `frontend/src/pages/AgentCenter/MyAssistant/AddMemberDrawer.tsx`
- Delete `frontend/src/pages/AgentCenter/MyAgent/`
- Delete `frontend/src/pages/AgentCenter/TeamConfig/`
- Import `../agent-center.css`

**Step 4.1** `AddMemberDrawer.tsx`：候选列表 + 搜索 + 加入按钮。Props：`open`、`onClose`、`onAdded`、`existingIds`。内部调用 `agentApi.candidates(keyword)`、`agentApi.addMember(id)`；过滤 `existingIds`。

**Step 4.2** `MyAssistant/index.tsx` 数据加载：

```tsx
const [me, setMe] = useState<any>(null)
const [team, setTeam] = useState<TeamMember[]>([])
const [conversations, setConversations] = useState<ConversationItem[]>([])
const canManageTeam = useAuthStore(s => s.hasPermission)('ai.agent.assistant', 'read')

const load = useCallback(async () => {
  const [meRes, teamRes, convRes]: any = await Promise.all([
    agentApi.me(),
    agentApi.team().catch(() => ({ data: { items: [] } })),
    agentApi.conversations({ page_size: 50 }).catch(() => ({ data: { items: [] } })),
  ])
  setMe(meRes.data)
  setTeam(teamRes.data?.items || [])
  setConversations(convRes.data?.items || [])
}, [])
```

**Step 4.3** 页面结构（沿用设计文档 4.1）：

- `PageHeader` + 打开助手 / 新建对话。
- 4 个 `StatCard`：团队成员、近 7 天对话、近 7 天 Token、最近调用。
- `ai-two-col`：团队成员卡（`ai-team-grid`，成员卡含移除 Popconfirm；右上「添加成员」打开抽屉）+ 团队能力卡（能力 chips、技能列表）。
- `ai-two-col.reverse`：最近会话卡（列表，继续/查看）+ 最近调用卡（紧凑 Table）。
- 会话查看抽屉复用 `agentApi.conversation(id)` + `Markdown`。
- 空态与错误态：Empty + 重试。

**Step 4.4** 验证：`npm run build`；手动检查 `/agents`。

---

## Task 5: 智能体管理 — 页壳 + 智能体目录

**Files:**
- Rewrite `frontend/src/pages/AgentCenter/Admin/index.tsx`
- Create `frontend/src/pages/AgentCenter/Admin/AgentDirectoryTab.tsx`
- Create `frontend/src/pages/AgentCenter/Admin/AgentEditDrawer.tsx`

**Step 5.1** `AgentEditDrawer.tsx`：把原 Admin 的 Modal 表单迁入 Drawer。

- Props：`open`、`agent: any | null`、`onClose`、`onSaved`。
- 打开时加载 `agentApi.capabilities()`、`agentApi.adminSkills({ page_size: 100 })`、`userApi.roles({ page_size: 500 })`。
- 表单字段与原逻辑一致：名称、能力、技能、开放范围、开放角色、说明、启用。
- 提交 payload 与原 `submitAgent` 一致。
- Drawer 底部固定「取消 / 保存」。

**Step 5.2** `AgentDirectoryTab.tsx`：

- Props：`createSignal: number`、`onBindUsers: (ids: number[]) => void`。
- 自身状态：agents、total、page、keyword、status、loading、editing、editOpen。
- `useEffect` 监听 `createSignal` > 0 时打开新建抽屉。
- 工具栏：`Input.Search`（名称/编号）、状态 `Select`、右侧计数。
- 卡片网格：`ai-agent-grid` + `ai-agent-card`；卡片字段与设计文档 4.2 一致。
- 分页：`Pagination` 6/页。
- 空态：Empty + 「新建智能体」。
- 编辑器：`AgentEditDrawer`，保存后刷新列表。

**Step 5.3** `Admin/index.tsx`：

- 状态：`zone`（`agents | skills | ops`）、`stats`、`bindOpen`、`bindAgentIds`、`createSignal`。
- 顶部 `PageHeader`：标题「智能体管理」、副标题、右侧「批量绑定用户」「新建智能体」。
- 4 个 `StatCard`：智能体总数、启用、能力调用、失败/超时/拒绝。
- `Tabs` 三个区：智能体（`AgentDirectoryTab`）、技能库（`SkillLibraryTab`）、助手运营（`AssistantOpsTab`）。
- 「新建智能体」：`setZone('agents'); setCreateSignal(v => v + 1)`。
- `BindUsersModal` 保留在页级。

**Step 5.4** 验证：`npm run build`；手动检查 `/agents/admin` 智能体区。

---

## Task 6: 技能库重做

**Files:**
- Rewrite `frontend/src/pages/AgentCenter/Admin/SkillLibraryTab.tsx`
- Rewrite `frontend/src/pages/AgentCenter/Admin/BindUsersModal.tsx`（仅样式容器与 `ac-fs-xs` → `sc-sub`）

**Step 6.1** 技能库外层改为：

```tsx
<div className="ai-card">
  <div className="ai-card-head">
    <h3>技能库</h3>
    <span className="ai-hint">技能以磁盘文件夹为准，SKILL.md 定义能力说明</span>
    <div className="ai-more">
      <Space wrap>
        {/* 搜索 / 来源 / 状态 / 同步 / 导入 */}
      </Space>
    </div>
  </div>
  <div className="ai-card-body" style={{ padding: 0 }}>
    <Table ... />
  </div>
</div>
```

- 保留所有 API 与操作；移除 `className="ac-fs-xs"`，改用 `sc-sub`。
- 表格 `size="small"`，`scroll={{ x: 900 }}` 防挤压。
- 预览 Drawer 保持功能，按钮/标签套用 `sc-tag`。

**Step 6.2** `BindUsersModal`：在 `<Form>` 外包 `<div className="sc-page">`；`ac-fs-xs` 改 `sc-sub`。

**Step 6.3** 验证：`npm run build`；手动检查技能同步/导入/预览。

---

## Task 7: 助手运营（概览 / 运行记录 / 调用审计 / 会话审计 / 配置）

**Files:**
- Create `frontend/src/pages/AgentCenter/Admin/AssistantOpsTab.tsx`
- Create `frontend/src/pages/AgentCenter/Admin/AssistantOpsPanels.tsx`
- Rewrite `frontend/src/pages/AgentCenter/Admin/AssistantConfigTab.tsx`
- Delete `frontend/src/pages/AgentCenter/Admin/AssistantMonitorTab.tsx`

**Step 7.1** `AssistantOpsPanels.tsx` 从旧 `AssistantMonitorTab` 与旧 Admin 迁移：

```tsx
export function AssistantOverviewPanel({ days }: { days: number }) { ... }
export function AssistantRunsPanel({ days }: { days: number }) { ... }
export function AgentCallsPanel() { ... }
export function ConversationAuditPanel() { ... }
```

- 概览：5 张 `StatCard` + 两个 `ai-card` 图表（沿用 `@ant-design/charts` 的 `Column`）。
- 运行记录：`ai-card` + Table + trace 详情 Modal，保留全部字段。
- 调用审计：旧 Admin 的 `calls` 查询与列迁移过来。
- 会话审计：输入会话 ID + 原因 + 查看按钮，结果抽屉保留留痕说明。

**Step 7.2** `AssistantOpsTab.tsx`：

```tsx
const [panel, setPanel] = useState('overview')
return (
  <div className="ai-ops">
    <Segmented
      value={panel}
      onChange={value => setPanel(String(value))}
      options={[
        { value: 'overview', label: '概览' },
        { value: 'runs', label: '运行记录' },
        { value: 'calls', label: '调用审计' },
        { value: 'audit', label: '会话审计' },
        { value: 'config', label: '助手配置' },
      ]}
    />
    <div style={{ marginTop: 12 }}>
      {panel === 'overview' && <AssistantOverviewPanel days={30} />}
      {panel === 'runs' && <AssistantRunsPanel days={30} />}
      {panel === 'calls' && <AgentCallsPanel />}
      {panel === 'audit' && <ConversationAuditPanel />}
      {panel === 'config' && <AssistantConfigTab />}
    </div>
  </div>
)
```

**Step 7.3** `AssistantConfigTab.tsx`：保留提示词 / 模型参数 / 保存逻辑；外层改用 `ai-card` + `ai-card-head`，说明条改用 `sc-sync-bar` 或浅靛蓝提示条；删除 `sc-page` 外层的重复。

**Step 7.4** 验证：`npm run build`；手动检查运营五个二级页。

---

## Task 8: AI 智能助手 — 页面骨架与历史会话

**Files:**
- Create `frontend/src/components/Assistant/types.ts`
- Create `frontend/src/components/Assistant/ChatHistorySidebar.tsx`
- Create `frontend/src/components/Assistant/AssistantContextRail.tsx`
- Create `frontend/src/components/Assistant/ChatComposer.tsx`
- Create `frontend/src/components/Assistant/assistant.css`
- Rewrite `frontend/src/pages/Assistant/index.tsx`
- Delete `frontend/src/pages/Assistant/assistant.css`

**Step 8.1** `types.ts`：

```ts
import { AgentSkillBrief } from '../../services/agent'

export interface TeamAgent {
  id: number
  name: string
  capabilities?: Array<{ code: string; name: string }>
  skills?: AgentSkillBrief[]
}
```

**Step 8.2** `ChatHistorySidebar.tsx`：

- Props：`conversations`、`loading`、`activeId`、`onNew`、`onOpen`、`teamCount`。
- 按 `last_message_at` 分组「今天 / 更早」，今天与更早各按时间倒序。
- 空态、加载态。
- 底部 `团队成员 N` + 点击跳 `/agents`。
- 样式类：`ai-chat-side`、`ai-side-new`、`ai-side-group`、`ai-side-item`。

**Step 8.3** `AssistantContextRail.tsx`：

- Props：`teamAgents: TeamAgent[]`、`messages: ChatMessage[]`。
- 聚合能力：`teamAgents.flatMap(a => a.capabilities || [])` 去重。
- 聚合技能：`teamAgents.flatMap(a => a.skills || [])` 去重。
- 当前执行链：从后往前找 `msg.plan` 或 `msg.steps?.length` 的 assistant 消息。
- 三块：团队成员、能力与技能、本会话执行链；空态提示。
- 样式类：`ai-context`、`ai-context-body`、`ai-context-section`。

**Step 8.4** `ChatComposer.tsx`：

- Props：`value`、`onChange`、`onSend`、`loading`、`onStop`、`disabled`、`placeholder`、`inputRef`。
- 使用 `Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }}`，`variant="borderless"`。
- Enter 发送、Shift+Enter 换行。
- 发送按钮圆形靛蓝；loading 时停止按钮。
- 底部提示：`Enter 发送 · Shift+Enter 换行`。

**Step 8.5** `assistant.css`：三栏布局、消息、计划/步骤、确认卡、诊断、使用 `--ai-*` 变量。关键布局：

```css
.ai-chat-page { height: calc(100vh - 124px); min-height: 560px; }
.ai-chat {
  display: flex; height: 100%; min-height: 0; overflow: hidden;
  background: #fff; border: 1px solid var(--ai-border);
  border-radius: 12px; box-shadow: var(--ai-shadow);
}
.ai-chat-side {
  width: 280px; flex: none; min-height: 0; display: flex; flex-direction: column;
  border-right: 1px solid var(--ai-border); background: #fbfcfe;
}
.ai-chat-main { flex: 1; min-width: 0; display: flex; flex-direction: column; background: #fff; }
.ai-chat-head {
  height: 52px; flex: none; display: flex; align-items: center; gap: 10px;
  padding: 0 16px; border-bottom: 1px solid var(--ai-border);
}
.ai-chat-body { flex: 1; min-height: 0; overflow: auto; padding: 24px 28px; }
.ai-chat-stream { max-width: 760px; margin: 0 auto; }
.ai-chat-context {
  width: 300px; flex: none; min-height: 0; overflow: auto;
  border-left: 1px solid var(--ai-border); background: #fbfcfe;
}
.ai-composer { flex: none; padding: 12px 28px 16px; border-top: 1px solid var(--ai-border); }
.ai-composer-box {
  max-width: 760px; margin: 0 auto; display: flex; align-items: flex-end; gap: 8px;
  padding: 8px 8px 8px 14px; border: 1px solid var(--ai-border);
  border-radius: 12px; background: #fff; box-shadow: var(--ai-shadow);
}
.ai-composer-box:focus-within {
  border-color: var(--ai-brand);
  box-shadow: 0 0 0 3px rgba(91, 91, 214, .14);
}
@media (max-width: 1200px) { .ai-chat-context { display: none; } }
@media (max-width: 960px) {
  .ai-chat-side { display: none; }
  .ai-chat-body { padding: 18px 16px; }
  .ai-composer { padding: 10px 16px 14px; }
}
```

**Step 8.6** `pages/Assistant/index.tsx`：

- `teamAgents` 类型改为 `TeamAgent`（含 skills）。
- 加载 `agentApi.me()` / `agentApi.team()` / `agentApi.conversations`。
- 状态：`activeConversationId`、`contextOpen`、`historyOpen`。
- 结构：

```tsx
<div className="sc-page ai-center ai-chat-page">
  <div className="ai-chat">
    <ChatHistorySidebar ... />
    <div className="ai-chat-main">
      <div className="ai-chat-head">
        <span className="ai-online-dot" />
        <strong>AI 智能助手</strong>
        <span className="ai-muted">{teamAgents.length} 位团队成员</span>
        <div className="ai-chat-head-actions">
          <Button type="text" size="small" icon={<HistoryOutlined />} className="ai-history-toggle" onClick={() => setHistoryOpen(true)}>
            历史
          </Button>
          <Button type="text" size="small" icon={<ClearOutlined />} disabled={!messages.length} onClick={newChat}>清空</Button>
          <Button type="text" size="small" onClick={() => setContextOpen(v => !v)}>
            {contextOpen ? '收起上下文' : '展开上下文'}
          </Button>
        </div>
      </div>
      <ChatPanel ... />
    </div>
    {contextOpen && <AssistantContextRail teamAgents={teamAgents} messages={messages} />}
  </div>
  <Drawer placement="left" width={300} open={historyOpen} onClose={() => setHistoryOpen(false)}>
    <ChatHistorySidebar ... />
  </Drawer>
</div>
```

- `ChatPanel` props 保持不变；新增 `teamAgents` 类型引用。

**Step 8.7** 验证：`npm run build`；手动检查三栏布局、折叠、历史切换。

---

## Task 9: ChatPanel 重写

**Files:**
- Rewrite `frontend/src/components/Assistant/ChatPanel.tsx`
- Modify `frontend/src/components/Assistant/ClarificationCard.tsx`（移除 `ac-fs-sm`）

**Step 9.1** 保留 `formatTimestamp`、`getProviderLabel`、`STEP_STATUS_META`、自动滚动逻辑、Clarification 解析。

**Step 9.2** 空态：助手标识 + 标题 + 副标题 + 4 张场景卡 + 团队成员 chip：

```tsx
const SCENES = [
  { icon: <WarningOutlined />, title: '查交付风险', hint: '哪些订单快延期了？', prompt: '今天有哪些订单存在交付风险？' },
  { icon: <AppstoreOutlined />, title: '看物料齐套', hint: '齐套率与缺料', prompt: '当前齐套率怎么样？缺哪些料？' },
  { icon: <BugOutlined />, title: '分析异常', hint: '异常池与品质问题', prompt: '帮我分析当前未闭环的异常。' },
  { icon: <EditOutlined />, title: '修改交期', hint: '确认后写回订单', prompt: '帮我修改订单的交期。' },
]
```

点击场景卡：`setInputValue(scene.prompt); inputRef.current?.focus()`。

**Step 9.3** 用户消息：

```tsx
<div className="ai-msg user">
  <div className="ai-bubble-user">{msg.content}</div>
</div>
```

**Step 9.4** 助手消息：

```tsx
<div className="ai-msg assistant">
  <div className="ai-msg-avatar"><RobotOutlined /></div>
  <div className="ai-msg-main">
    {thinking...}
    {displayContent && <Markdown>{displayContent}</Markdown>}
    {clarification && <ClarificationCard ... />}
    {msg.plan && <PlanCard ... />}
    {msg.steps?.length > 0 && <StepTimeline ... />}
    {msg.confirmation && <ConfirmationCard ... />}
    {suggestions...}
    {diagnostics...}
    {meta...}
  </div>
</div>
```

**Step 9.5** `PlanCard` / `StepTimeline` / `ConfirmationCard` / `Diagnostics` 使用 `ai-plan`、`ai-steps`、`ai-confirm`、`ai-diagnostic` 类；字段与逻辑不变。

**Step 9.6** 输入区使用 `ChatComposer`；`hasPendingConfirmation` 时 placeholder 改为「请先确认上方写操作卡片」。

**Step 9.7** 验证：`npm run build`；手动发消息、流式、停止、计划/步骤、确认卡、清空、历史会话加载。

---

## Task 10: 清理与入口换色

**Files:**
- Modify `frontend/src/components/Assistant/AssistantLauncher.tsx`
- Modify `frontend/src/index.css`
- Delete `frontend/src/pages/AgentCenter/Admin/AssistantMonitorTab.tsx`（Task 7 已删）
- Delete old `pages/Assistant/assistant.css`（Task 8 已删）

**Step 10.1** `AssistantLauncher` 背景与阴影改为靛蓝：

```tsx
background: 'linear-gradient(135deg, #7a7de6 0%, #5b5bd6 100%)',
boxShadow: hovering ? '0 10px 28px rgba(91,91,214,.45)' : '0 6px 20px rgba(91,91,214,.32)',
```

**Step 10.2** 删除 `frontend/src/index.css` 中 `.agent-center-page` 整块（约 2828–2875 行）。

**Step 10.3** 全局残留检查：

```bash
rg "agent-center-page|ac-fs-|AssistantMonitorTab|pages/AgentCenter/MyAgent|pages/AgentCenter/TeamConfig" frontend/src
```

Expected: 无命中。

---

## Task 11: 构建与回归

**Step 11.1** 前端构建：

```bash
cd frontend
npm run build
```

Expected: `tsc -b && vite build` 成功。

**Step 11.2** 后端测试：

```bash
cd backend
python -m pytest
```

Expected: 全量通过；若环境缺依赖，记录并至少跑 `python -m pytest tests/integration -q`。

**Step 11.3** 手动验收清单：

- `admin`：菜单「智能中心」下仅「我的助手」「智能体管理」。
- `/agents`：KPI、团队成员增删、能力/技能、最近会话、最近调用。
- `/agents/admin`：三区切换、卡片目录、新建/编辑抽屉、批量绑定、技能同步/导入/预览、运营五个二级页。
- `/ai-assistant`：三栏布局、空态场景卡、发消息、停止、计划/步骤、确认卡、历史会话切换、上下文折叠。
- 非管理账号：管理菜单不可见；无 `ai.agent.assistant` 账号团队成员区只读。
- 刷新和直接访问 `/agents`、`/agents/admin`、`/ai-assistant` 均正常。

---

## Self-Review

- 覆盖设计文档全部决策：四页、三区、合并用户页、三栏聊天、卡片目录、不接卡片、sc-page 复用。
- 无 TBD/TODO；所有新增文件路径明确。
- 后端仅权限元数据与启动迁移，不动 API。
- 删除项均有对应新实现，避免死代码。
