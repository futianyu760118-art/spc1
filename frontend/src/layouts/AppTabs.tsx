import { useMemo } from 'react'
import { Dropdown } from 'antd'
import { CloseOutlined, MoreOutlined, ReloadOutlined } from '@ant-design/icons'
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

  // 标题在渲染时由菜单树推导（单一来源，菜单改名自动跟随）
  const titles = useMemo(() => {
    const map: Record<string, string> = {}
    for (const t of tabs) {
      const crumb = resolveCrumb(navTree, t.pathname)
      map[t.key] = crumb.page || t.pathname
    }
    return map
  }, [tabs, navTree])

  const handleClose = (key: string) => {
    const neighbor = useTabsStore.getState().close(key)
    if (neighbor) appHistory.replace(tabUrl(neighbor))
  }

  const handleMenu = ({ key }: { key: string }) => {
    const store = useTabsStore.getState()
    if (!store.activeKey) return
    if (key === 'refresh') {
      store.refreshActive()
    } else if (key === 'closeOthers') {
      store.closeOthers(store.activeKey)
    } else if (key === 'closeAll') {
      const home = store.closeAll()
      if (home) appHistory.replace(tabUrl(home))
    }
  }

  return (
    <div className="app-tabs-bar">
      <div className="app-tabs-scroll">
        {tabs.map((t) => (
          <div
            key={t.key}
            className={`app-tab${t.key === activeKey ? ' active' : ''}`}
            onClick={() => {
              if (t.key !== activeKey) appHistory.push(tabUrl(t))
            }}
          >
            <span className="app-tab-title">{titles[t.key]}</span>
            {!t.pinned && (
              <span
                className="app-tab-close"
                onClick={(e) => {
                  e.stopPropagation()
                  handleClose(t.key)
                }}
              >
                <CloseOutlined />
              </span>
            )}
          </div>
        ))}
      </div>
      <Dropdown
        trigger={['click']}
        menu={{
          items: [
            { key: 'refresh', icon: <ReloadOutlined />, label: '刷新当前页签' },
            { key: 'closeOthers', label: '关闭其他页签' },
            { key: 'closeAll', label: '关闭全部页签' },
          ],
          onClick: handleMenu,
        }}
      >
        <div className="app-tabs-more" title="页签管理">
          <MoreOutlined />
        </div>
      </Dropdown>
    </div>
  )
}
