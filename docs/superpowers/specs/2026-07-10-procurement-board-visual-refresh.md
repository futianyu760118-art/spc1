# 采购看板样式现代化改造

**日期**: 2026-07-10
**范围**: `frontend/src/pages/Dashboard/components/ProcurementBoard/index.tsx`（仅样式层）
**目标**: 把看板视觉对齐到系统统一的玻璃拟态 + indigo 主题风格

## 背景

`ProcurementBoard`（采购看板）当前使用一套内联 CSS 自写的老式样式：

- 硬阴影 `box-shadow: 0 2px 6px rgba(0,0,0,0.06)`
- 6px 实心左边条 `#e53e3e / #dd6b20 / #38a169`
- 卡片背景满色 `#fff5f5 / #fffaf0 / #f0fff4`
- 列头红/蓝实色渐变条
- 厚重 `font-weight: 800` + `font-size: 1.4em` 的物料编号
- 浅灰背景 `#f7f9fc`

这些与系统中其他页面的 `card-modern`（玻璃模糊 + rgba 背景）、`stat-card`（indigo 渐变顶部线 + 软阴影）、`filter-bar` 等风格脱节，看上去"老"。

## 设计方案

### 1. 顶部 header（日期选择 / 责任人筛选 / 工具按钮）
- 套用全局 `.filter-bar` 玻璃容器
- 内边距 14px 20px，间距统一
- 工具按钮改为统一圆角 icon button（hover 背景 `rgba(99,102,241,0.08)`，激活态用 indigo 主色）

### 2. 列头（已逾期 / 正常-应到）
- 去掉红/蓝实色渐变条
- 玻璃拟态白底 `rgba(255,255,255,0.72)` + `backdrop-filter: blur(14px)`
- 顶部一条 3px 渐变线作为状态色标识：
  - 已逾期：`linear-gradient(90deg, #e11d48, #fb7185)` 玫红
  - 正常-应到：`linear-gradient(90deg, #6366f1, #818cf8)` 靛蓝
- 标题左侧保留图标（`WarningOutlined` / `CheckCircleOutlined`），右侧数字改为玻璃态徽章
- 字号统一 `calc(1rem * var(--font-size-scale))`

### 3. 卡片（核心改造）
- 玻璃拟态白卡 `rgba(255,255,255,0.78)` + `backdrop-filter: blur(16px) saturate(1.4)`
- 边框 `1px solid rgba(226,232,240,0.8)`，圆角 14px
- 去掉 6px 实心左边条，改为顶部一条 2px 渐变线（按状态变色）：
  - 逾期：`#e11d48 → #fb7185`
  - 欠料：`#d97706 → #fbbf24`
  - 已齐：`#059669 → #34d399`
  - 今日到期：`#d4380d → #f97316`
  - 明日到期：`#0ea5e9 → #38bdf8`
- 状态色用 pill 形式：浅色背景 + 深色字
  - `.pb-badge-danger`：`bg #fee2e2 / color #b91c1c`
  - `.pb-badge-warning`：`bg #fef3c7 / color #b45309`
  - `.pb-badge-success`：`bg #d1fae5 / color #047857`
  - `.pb-badge-today`：`bg #ffedd5 / color #c2410c`
  - `.pb-badge-info`：`bg #dbeafe / color #1d4ed8`
- 数字使用 `font-variant-numeric: tabular-nums`，弱化粗体（`font-weight: 600`），强化字号层级
- 物料名称/规格单行省略号，溢出显示省略号
- hover：上浮 3px + 阴影 `0 12px 32px rgba(15,23,42,0.10)` + 状态色淡光晕

### 4. 进度条
- 圆角加大到 999px（胶囊形）
- 背景 `rgba(99,102,241,0.08)`，填充用渐变
- 高度 8px

### 5. 图表（状态分布 / 责任人 / 齐套率）
- 已用 `.card-modern`，无大改
- 仅把图表标题与卡片内边距与新看板对齐（保持 16px 20px）
- 图表颜色映射同步更新到新色系

### 6. 保留不动
- 数据请求、刷新逻辑、筛选、全屏、图表交互
- 字段定义 `BoardItem` / `BoardData`
- `--font-size-scale` 全局字号缩放
- 响应式断点（1100px）

## 涉及修改文件

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/pages/Dashboard/components/ProcurementBoard/index.tsx` | 重写内联 `css` 模板，调整 className 与部分 JSX 内联样式（如 `bg / border / background`） |

## 验收标准

1. 看板视觉与系统其他页面（Dashboard 其它 tab、`stat-card`、`filter-bar`）风格一致
2. 玻璃模糊效果在 Chrome / Edge 正常显示
3. 状态色通过顶部渐变线 + pill 徽章清晰传达，无老式的整卡满色背景
4. 字号缩放 `--font-size-scale` 仍生效
5. 现有交互（刷新、全屏、筛选、图表切换）全部正常
6. `npm run lint` 与 `npm run typecheck` 通过（项目若配置）
