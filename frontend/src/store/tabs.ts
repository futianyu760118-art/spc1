import { create } from 'zustand'

export interface AppTab {
  id: number
  key: string
  pathname: string
  search: string
  refreshKey: number
  pinned?: boolean
  lastActiveAt: number
}

const HOME_TAB_PATH = '/dashboard'
const MAX_TABS = 10
const SESSION_KEY = 'spc_tabs'

export function tabKeyOf(pathname: string, search: string): string {
  return `${pathname}${search || ''}`
}

let nextTabId = 1

function makeHomeTab(): AppTab {
  return { id: nextTabId++, key: HOME_TAB_PATH, pathname: HOME_TAB_PATH, search: '', refreshKey: 0, pinned: true, lastActiveAt: 0 }
}

type PersistedTab = { key: string; pathname: string; search: string }

function readSessionTabs(): PersistedTab[] {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as PersistedTab[]) : []
  } catch {
    return []
  }
}

function persist(tabs: AppTab[]) {
  const list: PersistedTab[] = tabs.map(({ key, pathname, search }) => ({ key, pathname, search }))
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(list))
  } catch { /* sessionStorage 不可用时静默降级，仅失去刷新恢复能力 */ }
}

function initialTabs(): AppTab[] {
  const home = makeHomeTab()
  const restored = readSessionTabs()
    .filter((t) => t.key !== home.key)
    .slice(0, MAX_TABS - 1)
    .map((t) => ({ ...t, id: nextTabId++, refreshKey: 0, lastActiveAt: 0 }))
  return [home, ...restored]
}

function touch(tabs: AppTab[], key: string): AppTab[] {
  const now = Date.now()
  return tabs.map((t) => (t.key === key ? { ...t, lastActiveAt: now } : t))
}

interface TabsState {
  tabs: AppTab[]
  activeKey: string | null
  openTab: (pathname: string, search: string) => void
  replaceTo: (pathname: string, search: string) => void
  syncActiveUrl: (pathname: string, search: string) => void
  syncFromUrl: (pathname: string, search: string) => void
  close: (key: string) => AppTab | null
  closeOthers: (key: string) => void
  closeAll: () => AppTab | null
  refreshActive: () => void
  reset: () => void
}

export const useTabsStore = create<TabsState>((set, get) => ({
  tabs: initialTabs(),
  activeKey: null,

  // 跨页 push：去重聚焦已有页签，否则新建（超限时驱逐最久未激活的非固定页签）
  openTab: (pathname, search) => {
    const key = tabKeyOf(pathname, search)
    const { tabs } = get()
    const existing = tabs.find((t) => t.key === key)
    let next = tabs
    if (!existing) {
      const tab: AppTab = { id: nextTabId++, key, pathname, search, refreshKey: 0, lastActiveAt: Date.now() }
      next = [...tabs, tab]
      if (next.length > MAX_TABS) {
        let victim: AppTab | null = null
        for (const t of next) {
          if (!t.pinned && (!victim || t.lastActiveAt < victim.lastActiveAt)) victim = t
        }
        if (victim) next = next.filter((t) => t !== victim)
      }
    }
    set({ tabs: touch(next, key), activeKey: key })
  },

  // replace：不新增历史条目。目标已开 → 激活并关闭当前页签（固定页签除外）；
  // 目标未开 → 当前激活页签就地更新为目标 URL
  replaceTo: (pathname, search) => {
    const key = tabKeyOf(pathname, search)
    const { tabs, activeKey } = get()
    if (!activeKey || activeKey === key) return
    if (tabs.some((t) => t.key === key)) {
      const active = tabs.find((t) => t.key === activeKey)
      const next = active?.pinned ? tabs : tabs.filter((t) => t.key !== activeKey)
      set({ tabs: touch(next, key), activeKey: key })
      return
    }
    get().syncActiveUrl(pathname, search)
  },

  // 同页导航（不新开页签的 push/replace）：就地更新当前激活页签的 URL；
  // id 不变 → 内容区不 remount，页面状态保留（keep-alive）
  syncActiveUrl: (pathname, search) => {
    const key = tabKeyOf(pathname, search)
    const { tabs, activeKey } = get()
    if (!activeKey || activeKey === key) return
    const existing = tabs.find((t) => t.key === key)
    if (existing) {
      set({ tabs: touch(tabs, key), activeKey: key })
      return
    }
    const active = tabs.find((t) => t.key === activeKey)
    if (!active) return
    if (active.pinned) {
      // 固定首页不就地变身：目标新建页签并激活
      get().openTab(pathname, search)
      return
    }
    set({
      tabs: tabs.map((t) =>
        t.key === activeKey ? { ...t, key, pathname, search, lastActiveAt: Date.now() } : t
      ),
      activeKey: key,
    })
  },

  // popstate/首次挂载：URL 与激活页签保持一致的唯一入口
  syncFromUrl: (pathname, search) => {
    const key = tabKeyOf(pathname, search)
    const { tabs, activeKey } = get()
    if (activeKey === key) return
    if (tabs.some((t) => t.key === key)) {
      set({ tabs: touch(tabs, key), activeKey: key })
    } else {
      get().openTab(pathname, search)
    }
  },

  // 关闭页签；关闭激活页签时返回相邻页签（供调用方 replace URL），否则返回 null
  close: (key) => {
    const { tabs, activeKey } = get()
    const idx = tabs.findIndex((t) => t.key === key)
    if (idx < 0 || tabs[idx].pinned) return null
    const next = tabs.filter((t) => t.key !== key)
    if (activeKey === key) {
      const neighbor = next[Math.min(idx, next.length - 1)] ?? null
      set({ tabs: next, activeKey: neighbor ? neighbor.key : null })
      return neighbor
    }
    set({ tabs: next })
    return null
  },

  closeOthers: (key) => {
    const { tabs } = get()
    set({ tabs: touch(tabs.filter((t) => t.pinned || t.key === key), key), activeKey: key })
  },

  closeAll: () => {
    const { tabs } = get()
    const pinned = tabs.find((t) => t.pinned) ?? makeHomeTab()
    set({ tabs: [pinned], activeKey: pinned.key })
    return pinned
  },

  refreshActive: () => {
    const { tabs, activeKey } = get()
    if (!activeKey) return
    set({
      tabs: tabs.map((t) => (t.key === activeKey ? { ...t, refreshKey: t.refreshKey + 1 } : t)),
    })
  },

  reset: () => {
    const home = makeHomeTab()
    set({ tabs: [home], activeKey: null })
  },
}))

useTabsStore.subscribe((state) => persist(state.tabs))
