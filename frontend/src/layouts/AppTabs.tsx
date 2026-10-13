import { useEffect, useMemo, useRef, useState } from 'react'
import { Dropdown } from 'antd'
import { CloseOutlined } from '@ant-design/icons'
import { Routes, useLocation } from 'react-router-dom'
import { useTabsStore, tabKeyOf, type AppTab } from '../store/tabs'
import { appHistory } from '../utils/appHistory'
import { resolveCrumb, type PermissionAwareItem } from './navUtils'
import { contentRoutes } from '../router/contentRoutes'

function tabUrl(t: AppTab): string {
  return `${t.pathname}${t.search}`
}

// keep-alive 内容区：每个已开页签常驻一份 Routes（非激活 display:none）
export function TabbedContent() {
  const tabs = useTabsStore((s) => s.tabs)
  const activeKey = useTabsStore((s) => s.activeKey)
  const location = useLocation()
  const displayKey = activeKey ?? tabKeyOf(location.pathname, location.search)
  return (
    <>
      {tabs.map((t) => (
        <div key={t.id} style={{ display: t.key === displayKey ? undefined : 'none' }}>
          <div key={t.refreshKey}>
            <Routes location={{ pathname: t.pathname, search: t.search }}>{contentRoutes}</Routes>
          </div>
        </div>
      ))}
    </>
  )
}

interface AppTabsProps {
  navTree: PermissionAwareItem[]
}

export default function AppTabs({ navTree }: AppTabsProps) {
  const tabs = useTabsStore((s) => s.tabs)
  const activeKey = useTabsStore((s) => s.activeKey)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [hiddenCount, setHiddenCount] = useState(0)
  const [scrolledLeft, setScrolledLeft] = useState(false)

  // 标题在渲染时由菜单树推导（单一来源，菜单改名自动跟随）
  const titles = useMemo(() => {
    const map: Record<string, string> = {}
    for (const t of tabs) {
      const crumb = resolveCrumb(navTree, t.pathname)
      map[t.key] = crumb.page || t.pathname
    }
    return map
  }, [tabs, navTree])

  const activateTab = (t: AppTab) => {
    if (t.key !== activeKey) appHistory.push(tabUrl(t))
  }

  const closeTab = (key: string) => {
    const neighbor = useTabsStore.getState().close(key)
    if (neighbor) appHistory.replace(tabUrl(neighbor))
  }

  // 右键菜单：刷新 / 关闭该页签 / 关闭其他 / 关闭全部（⋮ 按钮功能并入页签）
  const contextMenuFor = (t: AppTab) => ({
    items: [
      { key: 'refresh', label: '刷新当前页签' },
      ...(t.pinned ? [] : [{ key: 'close', label: '关闭该页签' } as const]),
      { key: 'closeOthers', label: '关闭其他页签' },
      { key: 'closeAll', label: '关闭全部页签' },
    ],
    onClick: ({ key }: { key: string }) => {
      const store = useTabsStore.getState()
      if (key === 'refresh') {
        store.refreshActive()
      } else if (key === 'close') {
        closeTab(t.key)
      } else if (key === 'closeOthers') {
        const before = store.activeKey
        store.closeOthers(t.key)
        if (before !== t.key) appHistory.push(tabUrl(t))
      } else if (key === 'closeAll') {
        const home = store.closeAll()
        if (home) appHistory.replace(tabUrl(home))
      }
    },
  })

  // 溢出统计（几何计算，滚动不改变溢出集合）+ 左渐隐状态
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const recompute = () => {
      let hidden = 0
      el.querySelectorAll<HTMLElement>('[data-tab-key]').forEach((node) => {
        if (node.offsetLeft + node.offsetWidth > el.clientWidth + 1) hidden += 1
      })
      setHiddenCount(hidden)
      setScrolledLeft(el.scrollLeft > 0)
    }
    recompute()
    const ro = new ResizeObserver(recompute)
    ro.observe(el)
    el.addEventListener('scroll', recompute)
    return () => {
      ro.disconnect()
      el.removeEventListener('scroll', recompute)
    }
  }, [tabs, titles])

  // 鼠标滚轮在页签条上直接横向滚动（需非 passive 才能 preventDefault）
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
      e.preventDefault()
      el.scrollLeft += e.deltaY
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  // 激活页签自动滚入视野
  useEffect(() => {
    if (!activeKey) return
    const nodes = scrollRef.current?.querySelectorAll<HTMLElement>('[data-tab-key]')
    if (!nodes) return
    for (const node of Array.from(nodes)) {
      if (node.dataset.tabKey === activeKey) {
        node.scrollIntoView({ block: 'nearest', inline: 'nearest' })
        break
      }
    }
  }, [activeKey])

  // 溢出「+N」下拉：列出全部页签，可跳转 / 可关闭
  const overflowMenu = {
    items: tabs.map((t) => ({
      key: t.key,
      label: (
        <span className={`app-tabs-overflow-item${t.key === activeKey ? ' active' : ''}`}>
          <span className="app-tabs-overflow-title">{titles[t.key]}</span>
          {!t.pinned && (
            <CloseOutlined
              className="app-tabs-overflow-close"
              onClick={(e) => {
                e.stopPropagation()
                closeTab(t.key)
              }}
            />
          )}
        </span>
      ),
    })),
    onClick: ({ key }: { key: string }) => {
      const t = useTabsStore.getState().tabs.find((x) => x.key === key)
      if (t) activateTab(t)
    },
  }

  return (
    <div className="app-tabs-bar">
      <div className="app-tabs-scroll" ref={scrollRef}>
        {tabs.map((t) => (
          <Dropdown key={t.key} trigger={['contextMenu']} menu={contextMenuFor(t)}>
            <div
              className={`app-tab${t.key === activeKey ? ' active' : ''}`}
              data-tab-key={t.key}
              onClick={() => activateTab(t)}
            >
              <span className="app-tab-title">{titles[t.key]}</span>
              {!t.pinned && (
                <span
                  className="app-tab-close"
                  onClick={(e) => {
                    e.stopPropagation()
                    closeTab(t.key)
                  }}
                >
                  <CloseOutlined />
                </span>
              )}
            </div>
          </Dropdown>
        ))}
      </div>
      {scrolledLeft && <div className="app-tabs-fade left" />}
      {hiddenCount > 0 && (
        <>
          <div className="app-tabs-fade right" />
          <Dropdown trigger={['click']} menu={overflowMenu}>
            <div className="app-tabs-overflow" title="被挤出的页签">
              +{hiddenCount}
            </div>
          </Dropdown>
        </>
      )}
    </div>
  )
}
