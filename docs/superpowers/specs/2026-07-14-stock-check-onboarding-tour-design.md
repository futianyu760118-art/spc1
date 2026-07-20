# Design: 物料盘点新手指引 (Stock Check Onboarding Tour)

**Date:** 2026-07-14
**Status:** Approved, pending implementation
**Scope:** Frontend only. Add an `antd.Tour` walkthrough on the StockCheck page, triggered automatically for first-time users and re-triggerable via a "?" help button. State persisted via the existing `sys_user.ui_preferences` JSONB column.

---

## 1. Background

物料盘点 (`scm_inventory_check`) 是新上线的功能。仓管员和采购员第一次进入 `/stock-check?orderNo=...` 时,面对搜索栏/创建按钮/物料表(三个数+差异)/操作按钮等多个新概念,需要一段引导。

需要的能力:
- **自动弹一次**(新用户首次访问)
- **不再骚扰**(看完或全局关闭后消失)
- **可随时重看**("?" 按钮)
- **跨设备一致**(状态写后端)

---

## 2. 已复用的基础设施

| 已存在 | 用途 |
|---|---|
| `sys_user.ui_preferences` JSONB 列 | 每用户 key-value 存储 |
| `PUT /api/v1/basicdata/auth/preferences` | 后端 API 接受任意 `ui_preferences` 字典 |
| `GET /api/v1/basicdata/auth/me` | 登录时回填到 `useUiPreferencesStore` |
| `useUiPreferencesStore` (Zustand) | localStorage + 后端双向同步 |
| `antd@5.22.6` 自带 `Tour` | 无需新依赖 |

**结论:零后端改动,零新依赖,只在前端 store 加 2 个方法。**

---

## 3. 数据结构

在 `preferences` JSONB 顶层新增 2 个 key:

```ts
preferences: {
  // 已有:列可见性
  [pageKey]: { visibleColumns: [...] },

  // 新增
  newbie_mode: true,                  // 全局开关,默认 true
  tours_seen: {                       // 每个 tour 单独记录
    stock_check: true,
  },
}
```

| 字段 | 类型 | 默认 | 用途 |
|---|---|---|---|
| `newbie_mode` | bool | `true` | 全局"开启新手指引"。设为 `false` → 永不弹任何 tour |
| `tours_seen.<tour_id>` | bool | 缺失 | 某个 tour 是否已看过 |

未来加新 tour (如 `kit_analysis_tour`),只需往 `tours_seen` 加新 key,不改架构。

---

## 4. 触发逻辑(两个独立 tour)

拆成两个 tour,各管各的视图,各看各的:

| Tour ID | 触发视图 | 步骤数 | 目标 |
|---|---|---|---|
| `stock_check_intro` | list view (`activeCheck === null`) | 2 | 搜索框 + 创建按钮 |
| `stock_check_detail` | detail view (`activeCheck !== null`) | 3 | 物料表 + 差异列 + 操作按钮 |

```ts
const tourId = activeCheck ? STOCK_CHECK_DETAIL_TOUR_ID : STOCK_CHECK_INTRO_TOUR_ID
const tourSteps = (activeCheck ? stockCheckDetailSteps! : stockCheckIntroSteps!) ?? []
const seenTour = useUiPreferencesStore(s => s.preferences?.['tours_seen']?.[tourId])

useEffect(() => {
  if (!newbieMode) return
  if (seenTour) return
  const t = setTimeout(() => setTourOpen(true), 500)
  return () => clearTimeout(t)
}, [newbieMode, seenTour, tourId])
```

| 条件 | 默认 | 控制 |
|---|---|---|
| `newbie_mode === true` | ✓ | 用户在 ? Popover 内可关闭 |
| `tours_seen[当前 tour_id] !== true` | ✓ | 看完或手动标记 |

**为什么不合并 5 步到一个 tour**:
- 步骤 2 (创建按钮) 只在 list view 渲染
- 步骤 3-5 (物料表/差异/操作) 只在 detail view 渲染
- 单个 tour 在 list view 弹 → step 3-5 找不到 target,popover 飘
- 单个 tour 在 detail view 弹 → step 2 找不到 target,popover 飘

> **重要: selector 必须返回稳定引用。** 不能写 `s.preferences?.['tours_seen'] ?? {}` (每次返回新 `{}` 触发无限重渲染),必须直接判断 `s.preferences?.['tours_seen']?.[tourId]` 返回 boolean。

---

## 5. 关闭/完成时

```ts
const handleTourClose = () => {
  const current = useUiPreferencesStore.getState().getFlag('tours_seen', {})
  useUiPreferencesStore.getState().setFlag('tours_seen', { ...current, stock_check: true })
}
```

`antd.Tour` 的 `onClose` 会在用户:
- 点 "完成" → 标记
- 点 mask 关闭 → 标记
- ESC 关闭 → 标记
- 主动点 Skip → 标记

即只要关掉就算"看完"。

---

## 6. UI 设计

### 6.1 搜索栏右侧"?"按钮 + Popover

```
┌─────────────────────────────────────┐
│  [搜索: ___]  [搜索]  [清空]  [?]   │  ← "?" 按钮
└─────────────────────────────────────┘
        │
        ▼ (点击 ? 弹出)
┌──────────────────────────┐
│  新手指引    [▶ 立即查看]  │
│  ──────────────────────  │
│  ☑ 开启新手指引 (默认开)  │
└──────────────────────────┘
```

- "立即查看" → `tourRef.current?.run()` (不重置 flag)
- 复选框 → `setFlag('newbie_mode', checked)`

### 6.2 Tour 5 步

用 `data-tour` 属性锚定元素 (比 ref 更灵活,避免与现有 ref 冲突):

| Step | target selector | 标题 | 说明 |
|---|---|---|---|
| 1 | `[data-tour="stock-check-search"]` | 1. 搜索订单 | 按订单号搜索,自动加载该订单的盘点单 |
| 2 | `[data-tour="stock-check-create"]` | 2. 创建盘点单 | 未找到盘点单时,点此按订单的 BOM 展开物料自动建单 |
| 3 | `[data-tour="stock-check-table"]` | 3. 物料表的三个数 | 应盘数=订单需求,库存数=系统当前库存,盘点数=你录入的实盘 |
| 4 | `[data-tour="stock-check-diff"]` | 4. 差异列 | 差异=盘点数-库存数。正数盘盈,负数盘亏 |
| 5 | `[data-tour="stock-check-actions"]` | 5. 操作按钮 | 保存全部/标记完成/取消。完结需所有行都已盘点 |

锚点位置(在 `StockCheck/index.tsx` 中):
1. 搜索栏 `<div>` 包装
2. "为 XX 创建盘点单" 按钮 (仅 `orderNo` 存在且无 activeCheck 时显示)
3. 物料表 `<Table>` 父容器
4. 物料表"差异"列 `<th>`
5. 顶部操作按钮区 `<Space>`

### 6.3 Tour 自身配置

```tsx
<Tour
  open={tourOpen}
  steps={stockCheckTourSteps}
  onClose={() => {
    handleTourClose()
    setTourOpen(false)
  }}
  onFinish={() => {
    handleTourClose()
    setTourOpen(false)
  }}
/>
```

---

## 7. Store 扩展 (frontend/src/store/uiPreferences.ts)

新增 2 个方法:

```ts
getFlag: (key: string, defaultValue: any = false) => {
  const v = get().preferences[key]
  return v === undefined ? defaultValue : v
},
setFlag: (key: string, value: any) => {
  const next = { ...get().preferences, [key]: value }
  set({ preferences: next })
  localStorage.setItem(UI_PREFS_KEY, JSON.stringify(next))
  authApi.updatePreferences({ ui_preferences: next }).catch((err: Error) => {
    console.error(`Failed to save UI flag [${key}]:`, err)
  })
},
```

与现有 `setColumnVisibility` 完全相同的 localStorage + 后端同步模式。

---

## 8. 设备维度

天然通过现有 `localStorage` + 后端合并机制:
- localStorage 立即生效 (同设备即时反馈)
- `authApi.updatePreferences` 写后端 (`sys_user.ui_preferences`)
- 重新登录时 `loadFromUser(user)` 把后端的 `tours_seen.stock_check: true` 拉到 localStorage → 不会重复弹
- 即使用户在新设备/新浏览器,只要用同一账号登录,行为一致

---

## 9. 文件清单 (3 个,无后端改动)

| 操作 | 文件 |
|---|---|
| 修改 | `frontend/src/store/uiPreferences.ts` (+ getFlag/setFlag) |
| 新建 | `frontend/src/pages/OrderDelivery/StockCheck/StockCheckTour.tsx` (5 步配置) |
| 修改 | `frontend/src/pages/OrderDelivery/StockCheck/index.tsx` (集成 antd.Tour + ? 按钮 + 5 个 data-tour) |

---

## 10. 验证清单

1. `npm run build` 通过
2. 新用户(清空 localStorage 的 `spc_ui_preferences` + 数据库无 `tours_seen`)首次进入 → 500ms 后 tour 自动弹
3. 关闭 tour → 刷新页面 → 不再自动弹
4. 点 ? 按钮 → tour 重新出现(不重置 flag)
5. 复选框取消 "开启新手指引" → 刷新 → 任何时候都不弹
6. 重新勾上 → 立即弹(因 tours_seen 已有,这是设计,用户主动重看场景)
7. 退出登录 → 重新登录 → tour 状态保留(后端有)
8. 后端数据库 `sys_user.ui_preferences.tours_seen.stock_check` 删除 → 重登录 → 重新弹
9. 多个 tour 互不干扰(预留扩展)

---

## 11. 风险/范围外

- 不做 tour 中途进度保存(用户中途关闭 = 看完,下次不弹,这是设计)
- 不做 tour 完成的差异提示(完成 vs 跳过 一致处理)
- 不做 tour 的"下一步跳转到 XX 页" (引导仅停留在 stock-check 页面内部)
- 不做服务端 analytics 埋点
