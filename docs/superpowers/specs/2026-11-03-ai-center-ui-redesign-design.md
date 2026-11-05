# 智能中心 UI 重设计 — 设计文档

- 日期：2026-11-03
- 状态：设计已确认（用户 2026-11-03 确认 IA、页面骨架、视觉规范与技术方案）
- 目标：按 `docs/prototype/redesign` 的「靛蓝精致版」风格，完全重构智能中心四个页面：我的助手、智能体管理、AI 智能助手，并同步收敛菜单与路由。

## 1. 背景与动机

当前智能中心存在以下问题：

- 我的智能体（`/agents/me`）与我的团队（`/agents/team`）分属两页，信息重复、跳转多。
- 智能体管理（`/agents/admin`）6 个 Tab 平铺，目录仍是密集表格，与全站已落地的 `sc-page` 靛蓝设计系统不一致。
- AI 智能助手页（`/ai-assistant`）是 AntD 卡片拼装：历史会话、对话、输入区风格割裂，缺少上下文与执行过程的可视化。
- 旧样式 `agent-center-page` 以 11–13px 小字为主，与原型 13–14px 的阅读节奏不一致。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| 范围 | 四页全量重做：我的助手、智能体管理（含全部 Tab/弹窗）、AI 智能助手；浮球/侧栏入口只换色 |
| IA 尺度 | 完全重新设计：可合并页面、重组 Tab、调整路由 |
| 助手页形态 | 对话工作台：历史会话 + 对话主区 + 可折叠上下文栏 |
| 管理页 IA | 6 Tab 收敛为三大区：智能体 / 技能库 / 助手运营（运营内二级导航） |
| 用户页 IA | 我的智能体 + 我的团队合并为「我的助手」 |
| 旧路由 | 直接改路由，不保留兼容 |
| 聊天业务卡片 | 不接回；只保留文字、计划、步骤、写操作确认 |
| 实现路径 | 复用全站 `.sc-page` 设计系统，新增模块级 `agent-center.css` |
| 管理页目录 | 卡片目录 + 编辑抽屉 |
| 权限重命名 | 旧 `ai.agent.self.me` / `ai.agent.team` 停用并废弃，新增 `ai.agent.assistant` 作为「我的助手」页权限；`ai.agent.self` 改为「智能中心」；`ai.agent.admin` 不变 |

## 3. 信息架构与路由

```
智能中心
├─ 我的助手        /agents          （原 /agents/me + /agents/team 合并）
└─ 智能体管理      /agents/admin    （原 6 Tab → 3 大区）
   ├─ 智能体       目录卡片 + 编辑抽屉 + 批量绑定用户
   ├─ 技能库       同步 / 导入 / 预览 / 启停 / 删除
   └─ 助手运营     概览 · 运行记录 · 调用审计 · 会话审计 · 助手配置

AI 智能助手        /ai-assistant    （顶栏浮球/侧栏入口进入，不进菜单）
```

路由改动：

- `/agents` → 我的助手（新）
- `/agents/admin` → 智能体管理（保留）
- 删除 `/agents/me`、`/agents/team`
- `/ai-assistant` → AI 智能助手（保留）

权限与菜单元数据：

- `ai.agent.self` 名称改为「智能中心」
- 新增 `ai.agent.assistant`，名称为「我的助手」，`route_path = /agents`
- 旧 `ai.agent.self.me` / `ai.agent.team` 停用并加入废弃清理清单，运行期由 `cleanup_deprecated_permissions` 删除；前端不再引用这两个码
- `ai.agent.admin` 不变
- 前端在「我的助手」页用 `ai.agent.assistant` 控制团队成员增删；无该权限时展示为只读列表

## 4. 页面设计

### 4.1 我的助手 `/agents`

```
我的助手  你的团队能力决定助手能做什么          [打开助手] [新建对话]
┌ 团队成员 ┐┌ 近7天对话 ┐┌ 近7天 Token ┐┌ 最近调用 ┐   ← sc-stat-card
┌──────────────── 团队成员 2fr ────────────────┐┌──── 1fr ────┐
│ [头像] 订单查询员  AG-0001  [启用]   [移除]    ││ 团队能力      │
│        能力·技能标签 / 说明                    ││ 能力 chips    │
│ [头像] 齐套分析员  AG-0002  [停用]   [移除]    ││ 技能列表      │
│ [+ 添加团队成员]                               ││              │
└──────────────────────────────────────────────┘└──────────────┘
┌──────────────── 最近会话 ────────────────────┐┌── 最近调用 ──┐
│ 标题 · 时间 · [继续] [查看]                    ││ 紧凑表格 5 行  │
└──────────────────────────────────────────────┘└──────────────┘
```

- 团队能力来自 `/agents/me` 的 `effective_capabilities` 与 `skills`。
- 团队成员来自 `/agents/me/team`；成员卡片两列，显示名称、编号、状态、能力、技能、说明。
- 添加成员沿用候选列表抽屉（`/agents/me/team/candidates`），加入/移出即时刷新。
- 最近会话来自 `/agents/me/conversations`，点击「继续」进入助手页；「查看」打开只读抽屉。
- 最近调用来自 `/agents/me` 的 `recent_calls`，紧凑表格展示成员、能力、状态、结果。
- 空态：团队成员为空时展示「还没有团队成员」并给出「添加第一个成员」；会话/调用为空时用 AntD Empty。

### 4.2 智能体管理 `/agents/admin`

```
智能体管理  管理目录、技能与助手运营            [批量绑定用户] [新建智能体]
┌ 智能体总数 ┐┌ 启用 ┐┌ 能力调用 ┐┌ 异常调用 ┐
[ 智能体 ] [ 技能库 ] [ 助手运营 ]              ← 大区级导航
┌ 搜索 ────────┐┌ 状态 ─┐                         共 N 个
┌ agent card ┐┌ agent card ┐┌ agent card ┐
│ 标识 名称   ││ ...        ││ ...        │
│ AG-xxxxx   ││            ││            │
│ 说明两行    ││            ││            │
│ 能力 / 技能 ││            ││            │
│ 开放范围 团队││            ││            │
│ [编辑][绑定]││            ││            │
└────────────┘└────────────┘└────────────┘
```

三大区：

1. **智能体**：卡片目录，支持关键字、状态筛选，分页 6 个；卡片含标识、名称、编号、说明、能力/技能标签、开放范围、勾选团队数、编辑与绑定入口。新建/编辑使用右侧 Drawer（基本信息 / 能力与技能 / 开放范围 / 说明与状态，底部固定保存）。批量绑定用户复用现有弹窗。
2. **技能库**：保留现有表格与预览抽屉，工具栏、表头、标签统一到设计系统。
3. **助手运营**：二级导航 `概览 | 运行记录 | 调用审计 | 会话审计 | 助手配置`。
   - 概览：5 张 KPI + 每日对话趋势 + 工具命中 Top10（现有数据）。
   - 运行记录：现有运行表 + trace 详情弹窗。
   - 调用审计：现有 `adminCalls` 列表（成员 / 能力 / 指令 / 状态 / 结果 / 耗时 / 时间）。
   - 会话审计：填写会话 ID 与原因后查看并留痕，抽屉展示消息。
   - 助手配置：提示词与模型参数，保留保存逻辑。

### 4.3 AI 智能助手 `/ai-assistant`

```
┌ 历史会话 280 ┬────────── 对话主区 ──────────┬ 上下文 300 ┐
│ [＋ 新建对话] │ AI 智能助手 · 在线      [收起] │ 团队成员   │
│ 今天          │                              │ 能力 / 技能│
│ · 会话 A      │   [空态 / 消息流]             │ 本会话执行链│
│ · 会话 B      │                              │            │
│ 更早          │                              │            │
│ · 会话 C      │ ┌──────────────────────────┐ │            │
│               │ │ 输入框            [发送]  │ │            │
└───────────────┴──────────────────────────────┴────────────┘
```

- 左栏：新建对话、按「今天 / 更早」分组的会话列表；当前会话靛蓝浅底 + 左侧 2px 竖条；底部展示团队成员数并链接到 `/agents`。
- 主区：页头显示标题、在线状态点、上下文栏开关；消息区最大宽度 760px 居中。
- 空态：助手标识 + 「今天想让助手做什么？」+ 4 张场景卡（查交付风险 / 看物料齐套 / 分析异常 / 修改交期）+ 团队成员 chip；点击场景卡填入输入框并聚焦。
- 消息：用户消息右侧靛蓝实底气泡；助手消息左侧头像 + 平铺 Markdown；时间与 Provider 为 11–12px 弱文。
- 执行计划与步骤：计划用带序号的紧凑清单（内容本身就是序列）；步骤用状态圆点 + 标签 + 耗时；错误通过 Tooltip 展示。
- 写操作确认：琥珀色卡片，字段「旧值 → 新值」，确认/取消按钮；执行结果用成功/失败提示。
- 建议问题：chip 形式，点击直接发送。
- 诊断信息：保留折叠面板，样式适配新卡片。
- 输入区：白色浮起卡片，TextArea 自适应 1–4 行，Enter 发送 / Shift+Enter 换行；加载中显示停止按钮；有待确认操作时提示先确认。
- 右栏：团队成员、团队能力与技能、当前回复的计划与步骤；可折叠；折叠状态仅保存在组件状态，不持久化：≥1200 默认展开，<1200 默认收起。

## 5. 视觉规范

在 `.ai-center` 内定义一次 CSS 变量，页面样式只引用变量：

| 用途 | 值 |
|---|---|
| 品牌主色 / hover | `#5b5bd6` / `#4c4dc2` |
| 品牌软底 / 描边 | `#eef0fe` / `#c6cbfa` |
| 主文 / 次文 / 弱文 | `#0f172a` / `#475569` / `#94a3b8` |
| 卡片边 / 页面底 | `#e2e8f0` / `#f8fafc` |
| 成功 / 警示 / 危险 / 信息 | `#16a34a` / `#d97706` / `#dc2626` / `#0284c7` |

- 排版：页面标题 20/600，副标题 13/400 弱文；卡片标题 14/600；正文 13.5–14；元信息 12；KPI 26/650 + `tabular-nums`。
- 结构：白卡 1px 边框 + 10px 圆角 + 轻阴影；卡片间距 12；卡片内边距 16；页头与内容间距 12。
- 不使用满屏渐变、不统一大圆角、不做彩色卡片墙。
- 动效：仅卡片 hover 边框、focus 靛蓝光环、流式脉冲；`prefers-reduced-motion: reduce` 时关闭非必要动效。
- AntD 控件样式沿用 `.sc-page` 现有的按钮 / 输入 / 表格 / 分页 / Tabs 覆盖，不重复定义。

## 6. 组件与文件改动

### 新增

- `frontend/src/pages/AgentCenter/agent-center.css`：模块级 token、页头、卡片目录、团队成员卡、KPI 区；我的助手 / 管理页 / 助手页共同导入（助手页另加 `assistant.css`）
- `frontend/src/components/Agent/PageHeader.tsx`：三页统一页头
- `frontend/src/components/Agent/StatCard.tsx`：从监控页抽出，供我的助手 / 管理页 / 运营概览复用
- `frontend/src/pages/AgentCenter/MyAssistant/index.tsx` + 成员添加抽屉
- `frontend/src/pages/AgentCenter/Admin/AgentDirectoryTab.tsx`
- `frontend/src/pages/AgentCenter/Admin/AgentEditDrawer.tsx`
- `frontend/src/pages/AgentCenter/Admin/AssistantOpsPanels.tsx`：概览 / 运行记录 / 调用审计 / 会话审计
- `frontend/src/components/Assistant/ChatHistorySidebar.tsx`
- `frontend/src/components/Assistant/AssistantContextRail.tsx`
- `frontend/src/components/Assistant/ChatComposer.tsx`
- `frontend/src/components/Assistant/assistant.css`：聊天工作台样式（作用域 `.ai-chat`）

### 重写

- `frontend/src/pages/Assistant/index.tsx`
- `frontend/src/components/Assistant/ChatPanel.tsx`
- `frontend/src/pages/AgentCenter/Admin/index.tsx`
- `frontend/src/pages/AgentCenter/Admin/AssistantConfigTab.tsx`
- `frontend/src/pages/AgentCenter/Admin/SkillLibraryTab.tsx`
- `frontend/src/pages/AgentCenter/Admin/BindUsersModal.tsx`
- `frontend/src/components/Agent/CapabilityTags.tsx`（改用 `sc-tag`，保留原 API）
- `frontend/src/components/Assistant/AssistantLauncher.tsx`（仅配色改为靛蓝）

### 删除

- `frontend/src/pages/AgentCenter/MyAgent/`
- `frontend/src/pages/AgentCenter/TeamConfig/`
- `frontend/src/pages/AgentCenter/Admin/AssistantMonitorTab.tsx`
- `frontend/src/pages/Assistant/assistant.css`
- `frontend/src/index.css` 的 `agent-center-page` 旧样式块

### 路由与菜单

- `frontend/src/router/contentRoutes.tsx`：新增 `/agents`，移除 `/agents/me`、`/agents/team`
- `frontend/src/layouts/MainLayout.tsx`：路径→权限映射改为 `/agents/admin`、`/agents`
- `backend/app/core/permission_registry.py`：更新名称与路由声明
- `backend/init_database.py`：更新 `migrate_agent_center_permissions`，把既有 DB 行的名称/路由回灌为「智能中心 / 我的助手 / 团队成员管理」，并把 `ai.agent.team.route_path` 置空

## 7. 数据与接口

- 不新增、不修改任何后端 API。
- 不修改 `useAssistantChat` 的 SSE 协议与消息结构。
- 不接回 `msg.cards` 业务卡片。
- 我的助手、智能体管理、助手运营全部复用现有 `agentApi` 方法。

## 8. 响应式与边界

- ≥1200：我的助手两栏、管理页三列卡片、助手页三栏。
- <1200：助手页右侧上下文栏默认收起；管理页卡片两列。
- <960：助手页历史会话改为抽屉入口；我的助手单栏；管理页卡片单列。
- 无权限：`ai.agent.admin` 无 read 时菜单不出现；`ai.agent.assistant` 无 read 时团队成员区只读。
- 接口失败：页面级错误用 Empty + 重试按钮；局部失败保留已加载数据并 toast 提示。
- 长文本：名称、说明、能力标签均 ellipsis 或换行限制；会话标题单行省略。

## 9. 验证

- 前端：`cd frontend && npm run build`
- 后端：`cd backend && python -m pytest`
- 手动：
  - `admin` 账号检查四页布局、目录编辑、绑定、技能操作、运营五个二级页。
  - 无 `ai.agent.admin` 的账号检查菜单不显示管理页。
  - 无 `ai.agent.assistant` 的账号检查团队成员区只读。
  - 助手页发消息、流式输出、停止、计划/步骤、写操作确认、历史会话切换。
- 全局残留：`rg "agents/me|agents/team|ai\.agent\.team|ai\.agent\.self\.me|agent-center-page|AssistantMonitorTab" frontend/src backend` 应仅剩 API 路径（`/agents/me/*` 接口）与测试路径。

## 10. 不做的事（YAGNI）

- 不恢复聊天业务卡片。
- 不新增会话搜索、重命名、删除（现有接口没有）。
- 不做仪表盘之外的 AI 用量分析/成本报表。
- 不改造浮球与侧栏入口的拖拽、收纳逻辑，仅换色。
- 不改 ERP、审批、订单写操作等任何业务链路。
